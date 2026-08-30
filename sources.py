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
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from config import JOURNALS, TOPICS, LOOKBACK_DAYS

OPENALEX_ENDPOINT = "https://api.openalex.org/works"

# One pooled session with browser-ish defaults. Nature and SpringerLink feeds
# sit behind a cookie/redirect bot check: a bare urllib request is served an
# HTML challenge page instead of the feed (this is what produced the
# "not well-formed (invalid token)" parse errors). requests gets through.
_HTTP = requests.Session()
_HTTP.headers.update(
    {"User-Agent": "aoi-bot/1.0 (+https://github.com/Li-Research-Group/aoi-bot)"}
)

# Feeds that carry no per-item date at all (ScienceDirect) can't be filtered
# by the lookback window, so cap how many of their ~100-item backlog we take.
_MAX_UNDATED_PER_FEED = 25


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

        dated = [e for e in entries if e["published"]]
        if entries and not dated:
            # No dates in this feed at all -- keep the newest handful
            # (publisher feeds are ordered newest-first).
            recent = entries[:_MAX_UNDATED_PER_FEED]
        else:
            recent = [e for e in dated if e["published"] >= cutoff]

        for entry in recent:
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
    """Fetch a feed URL and hand the bytes to _parse_feed_xml (split out so
    the parser can be tested against saved feed samples without a network
    call -- that's how the RSC bug below was originally caught)."""
    resp = _HTTP.get(feed_url, timeout=30)
    resp.raise_for_status()
    return _parse_feed_xml(resp.content)


# Namespaces seen across the publisher families we track. Nature feeds are
# RSS 1.0 / RDF (namespaced <item>, body in <content:encoded>, date in
# <dc:date>, DOI in <prism:doi>); ACS / RSC / SpringerLink / ScienceDirect
# are RSS 2.0; a few publishers emit Atom.
_FEED_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rss10": "http://purl.org/rss/1.0/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
}

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>&]+")
_DOI_LINE_RE = re.compile(r"\bDOI\s*:\s*10\.\d{4,9}/[^\s\"'<>&]+", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
# Publisher boilerplate that ends up in the body text. Each is trimmed only
# after the body has been reduced to a single line of plain text.
_RSS_COPYRIGHT_RE = re.compile(r"the content of this rss feed.*", re.IGNORECASE)
# RSC "Accepted Manuscript" / "Advance Article" feed items have no abstract --
# just a citation header, an Open-Access licence blurb, then the author list.
# Trim the header and licence cruft; whatever prose (if any) is left is kept.
_RSC_HEADER_RE = re.compile(
    r"^.{0,60}?,\s*\d{4},\s*(Accepted Manuscript|Advance Article)\b[,.]?\s*(Paper)?\s*",
    re.IGNORECASE,
)
_RSC_LICENSE_RE = re.compile(
    r"\s*(Open Access\s*)?(This article is licensed under[^.]*\.?|[\d\s]*Unported Licence\.?"
    r"|Creative Commons[^.]*\.?)",
    re.IGNORECASE,
)
# Nature prefixes the abstract with e.g. "Nature Water, Published online: 28
# August 2026; doi:10.1038/...;" -- strip up to and including that semicolon.
_PUBLISHED_ONLINE_PREFIX_RE = re.compile(r"^.{0,100}?Published online:[^;]*;\s*", re.IGNORECASE)
# ScienceDirect feeds carry no abstract -- just "Publication date: ... /
# Source: ... / Author(s): ...". Drop it so the entry has an empty abstract
# and the relevance filter skips it instead of spending a Claude call.
_SCIENCEDIRECT_META_RE = re.compile(r"^Publication date:.*", re.IGNORECASE)
_LEADING_LABEL_RE = re.compile(r"^(Abstract|Summary)\s+", re.IGNORECASE)


def _find_first(item, *tags):
    """First child element matching any of `tags` (prefixes resolved against
    _FEED_NS), else None. An explicit loop, not `a.find(x) or a.find(y)`: an
    element with text but no children is falsy in ElementTree, so `or` would
    skip a populated element."""
    for tag in tags:
        el = item.find(tag, _FEED_NS)
        if el is not None:
            return el
    return None


def _parse_feed_xml(raw: bytes) -> list[dict]:
    """Minimal RSS(2.0/1.0)/Atom parser -- avoids adding feedparser as a
    dependency. Handles the common subset of fields (title, link, body,
    date, authors, DOI) across the publisher families we track."""
    root = ET.fromstring(raw)

    items = root.findall(".//item")  # RSS 2.0
    if not items:
        items = root.findall(".//rss10:item", _FEED_NS)  # RSS 1.0 / RDF (Nature)
    if not items:
        items = root.findall(".//atom:entry", _FEED_NS)  # Atom

    entries = []
    for item in items:
        title = _text(_find_first(item, "title", "rss10:title", "atom:title", "dc:title"))

        link_el = _find_first(item, "link", "rss10:link", "atom:link")
        if link_el is not None and (link_el.text or "").strip():
            url = link_el.text.strip()
        elif link_el is not None:
            url = link_el.get("href", "")
        else:
            url = ""

        body_el = _find_first(
            item, "description", "rss10:description", "content:encoded",
            "dc:description", "atom:summary", "atom:content",
        )
        # itertext() so feeds that put real (unescaped) <p> children inside
        # <description> -- SpringerLink, ACS -- yield their text, not "".
        raw_body = "".join(body_el.itertext()) if body_el is not None else ""

        date_el = _find_first(
            item, "pubDate", "dc:date", "prism:publicationDate",
            "prism:coverDate", "atom:updated", "atom:published",
        )
        published = _parse_date(date_el.text) if date_el is not None and date_el.text else None

        authors = [e.text.strip() for e in item.findall("dc:creator", _FEED_NS) if (e.text or "").strip()]
        if not authors:
            authors = [
                e.text.strip()
                for e in item.findall("atom:author/atom:name", _FEED_NS)
                if (e.text or "").strip()
            ]

        doi_el = _find_first(item, "doi", "prism:doi", "dc:identifier")
        if doi_el is None:
            # ACS declares a broken prism namespace (xmlns:prism="prism"), so
            # match <doi> by local name regardless of namespace URI.
            doi_el = next(
                (e for e in item.iter() if e.tag.split("}")[-1].lower() == "doi"), None
            )
        doi = _normalize_doi(doi_el.text) if doi_el is not None else None
        if not doi:
            guid_el = item.find("guid")
            if guid_el is not None and (guid_el.text or "").strip().startswith("10."):
                doi = guid_el.text.strip()
        if not doi:
            doi = _extract_doi(raw_body) or _extract_doi(url)

        entries.append(
            {
                "title": title,
                "url": url,
                "abstract": _clean_description(raw_body),
                "published": published,
                "authors": authors,
                "doi": doi,
            }
        )
    return entries


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _normalize_doi(raw: str | None) -> str | None:
    """Bare-DOI form -- strips a 'doi:' or 'https://doi.org/' prefix so DOIs
    from RSS and from OpenAlex compare equal in dedupe()."""
    if not raw:
        return None
    doi = re.sub(r"^\s*(doi:|https?://(dx\.)?doi\.org/)", "", raw.strip(), flags=re.IGNORECASE)
    return doi.strip().rstrip(".,;)") or None


def _extract_doi(text: str) -> str | None:
    """Pull a DOI out of free text -- RSC embeds it in the description body
    (e.g. 'DOI: 10.1039/D6EE03332F') rather than in a dedicated field."""
    if not text:
        return None
    match = _DOI_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;)").strip() or None


def _clean_description(raw: str) -> str:
    """Reduce a feed body to plain abstract text: strip HTML (feeds double-
    encode, so unescape+strip twice), collapse whitespace, then trim
    publisher boilerplate -- RSC copyright/licence lines, the Nature
    'X, Published online: ...;' prefix, ScienceDirect metadata-only bodies,
    a leading 'Abstract' label. A metadata-only body trims to ''and the
    relevance filter then skips it without spending a Claude call."""
    if not raw:
        return ""
    text = raw
    for _ in range(2):
        text = _TAG_RE.sub(" ", html.unescape(text))
    text = re.sub(r"\s+", " ", text).strip()
    text = _RSS_COPYRIGHT_RE.sub("", text)
    text = _SCIENCEDIRECT_META_RE.sub("", text)
    text = _PUBLISHED_ONLINE_PREFIX_RE.sub("", text)
    text = _RSC_HEADER_RE.sub("", text)
    text = _DOI_LINE_RE.sub("", text)  # DOI is captured separately
    text = _RSC_LICENSE_RE.sub("", text)
    text = _LEADING_LABEL_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str) -> datetime.date | None:
    raw = raw.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
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
    # Every level here can be present-but-null in an OpenAlex record, so
    # coalesce with `or {}` before each .get() rather than chaining.
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in (work.get("authorships") or [])
    ]
    source = (work.get("primary_location") or {}).get("source") or {}
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    return {
        "title": work.get("title") or "",
        "authors": [a for a in authors if a],
        "journal": source.get("display_name") or "",
        "doi": _normalize_doi(work.get("doi")),
        "url": work.get("id") or "",
        "abstract": abstract,
        "published": work.get("publication_date") or "",
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
