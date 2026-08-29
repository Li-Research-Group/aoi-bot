"""
Pulls candidate papers from two lanes:

1. Journal RSS feeds (fast lane) -- guarantees same-day coverage for the
   journals we know matter, independent of any aggregator's ingestion lag.
2. OpenAlex topic search (broad lane) -- catches relevant papers outside
   the tracked journal list, using keyword queries per topic. OpenAlex is
   fully open, covers essentially any registered DOI (including paywalled
   publishers like ACS -- it indexes metadata, not full text, so paywalls
   don't block discovery), and updates daily.

Both lanes return a plain list of dicts with the same shape so downstream
code doesn't care which lane a paper came from:

    {
        "title": str,
        "authors": [str, ...],
        "journal": str,
        "doi": str | None,
        "url": str,
        "abstract": str,
        "published": "YYYY-MM-DD",
        "source_lane": "rss" | "openalex",
    }
"""

import datetime
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import requests

from config import JOURNALS, TOPICS, LOOKBACK_DAYS

OPENALEX_ENDPOINT = "https://api.openalex.org/works"


def _cutoff_date() -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)


def fetch_rss_candidates() -> list[dict]:
    """Fetch recent entries from every configured journal RSS feed."""
    cutoff = _cutoff_date()
    results = []
    for journal_name, feed_url in JOURNALS.items():
        if not feed_url or feed_url.startswith("FILL_IN"):
            continue
        try:
            entries = _parse_feed(feed_url)
        except Exception as exc:  # noqa: BLE001 -- log and keep going
            print(f"[warn] failed to fetch feed for {journal_name}: {exc}")
            continue
        for entry in entries:
            if entry["published"] and entry["published"] < cutoff:
                continue
            results.append(
                {
                    "title": entry["title"],
                    "authors": entry.get("authors", []),
                    "journal": journal_name,
                    "doi": entry.get("doi"),
                    "url": entry.get("url", ""),
                    "abstract": entry.get("abstract", ""),
                    "published": str(entry["published"]) if entry["published"] else "",
                    "source_lane": "rss",
                }
            )
    return results


def _parse_feed(feed_url: str) -> list[dict]:
    """Minimal RSS/Atom parser -- avoids adding feedparser as a dependency.
    Handles the common subset of fields (title, link, description, pubDate,
    dc:creator) that publisher feeds use."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": "aoi-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)

    ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/"}
    items = root.findall(".//item") or root.findall("atom:entry", ns)

    entries = []
    for item in items:
        title_el = item.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""

        link_el = item.find("link")
        if link_el is not None and link_el.text:
            url = link_el.text.strip()
        elif link_el is not None:
            url = link_el.get("href", "")
        else:
            url = ""

        desc_el = item.find("description") or item.find("atom:summary", ns)
        abstract = (desc_el.text or "").strip() if desc_el is not None else ""

        date_el = item.find("pubDate") or item.find("atom:updated", ns)
        published = _parse_date(date_el.text) if date_el is not None and date_el.text else None

        creator_el = item.find("dc:creator", ns)
        authors = [creator_el.text.strip()] if creator_el is not None and creator_el.text else []

        entries.append(
            {
                "title": title,
                "url": url,
                "abstract": abstract,
                "published": published,
                "authors": authors,
                "doi": None,
            }
        )
    return entries


def _parse_date(raw: str) -> datetime.date | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def fetch_openalex_candidates() -> list[dict]:
    """Query OpenAlex per topic keyword set for recent works."""
    cutoff = _cutoff_date().isoformat()
    results = []
    for topic_name, cfg in TOPICS.items():
        for keyword in cfg["keywords"]:
            params = {
                "search": keyword,
                "filter": f"from_publication_date:{cutoff}",
                "per-page": 10,
                "sort": "publication_date:desc",
            }
            url = f"{OPENALEX_ENDPOINT}?{urllib.parse.urlencode(params)}"
            try:
                resp = requests.get(url, timeout=20, headers={"User-Agent": "aoi-bot/1.0 (mailto:yalin.li@rutgers.edu)"})
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] OpenAlex query failed for '{keyword}': {exc}")
                continue

            for work in data.get("results", []):
                results.append(_openalex_to_paper(work))
            time.sleep(0.2)  # be polite to the API
    return results


def _openalex_to_paper(work: dict) -> dict:
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
    ]
    journal = (
        work.get("primary_location", {})
        .get("source", {})
        .get("display_name", "")
        if work.get("primary_location")
        else ""
    )
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    return {
        "title": work.get("title", "") or "",
        "authors": [a for a in authors if a],
        "journal": journal or "",
        "doi": work.get("doi"),
        "url": work.get("id", ""),
        "abstract": abstract,
        "published": work.get("publication_date", ""),
        "source_lane": "openalex",
    }


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as an inverted index (word -> positions).
    Reconstruct plain text from it."""
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _normalized_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def dedupe(papers: list[dict]) -> list[dict]:
    """Dedupe by DOI OR normalized title -- a paper can show up from RSS
    without a DOI and from OpenAlex with one, so checking only one key
    would miss that overlap."""
    seen_dois = set()
    seen_titles = set()
    unique = []
    for p in papers:
        doi_key = (p.get("doi") or "").lower()
        title_key = _normalized_title(p["title"])
        if (doi_key and doi_key in seen_dois) or (title_key and title_key in seen_titles):
            continue
        if doi_key:
            seen_dois.add(doi_key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(p)
    return unique
