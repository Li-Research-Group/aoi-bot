"""
Posts the weekly digest to Slack: a header message, then each paper and
each section separator as its own top-level channel message (not a
thread). Each paper is a distinct message so the reaction tracker
(track_reactions.py) can attach a per-paper thumbs-up/down count by ts.
"""

import datetime
import os

import requests

from config import SLACK_CHANNEL_ID

SLACK_API = "https://slack.com/api"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}", "Content-Type": "application/json"}


def post_message(text: str) -> dict:
    payload = {"channel": SLACK_CHANNEL_ID, "text": text}
    resp = requests.post(f"{SLACK_API}/chat.postMessage", headers=_headers(), json=payload, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack post failed: {data}")
    return data


def _oneline(s: str) -> str:
    """Collapse whitespace/newlines -- a stray newline in a title breaks the
    `<url|text>` link markup and garbles everything after it."""
    return " ".join((s or "").split())


def format_paper_message(paper: dict) -> str:
    author_list = paper.get("authors", []) or []
    authors = ", ".join(author_list[:3]) + (" et al." if len(author_list) > 3 else "")
    tags = " ".join(f"`[{t}]`" for t in paper.get("topics", []))
    link = paper.get("url") or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")

    cite = f"_{paper.get('journal', '')}_ ({paper.get('published') or 'n.d.'})"
    if authors:
        cite = f"{authors} — {cite}"
    if paper.get("title_only"):
        cite += "  ·  _matched on title only (no abstract available)_"

    lines = [
        tags,
        f"*<{link}|{_oneline(paper.get('title', ''))}>*",
        cite,
    ]
    if paper.get("reason"):
        lines.append(f"> {_oneline(paper['reason'])}")
    return "\n".join(line for line in lines if line)


def format_followed_author_message(paper: dict) -> str:
    who = ", ".join(paper.get("matched_authors", [])) or "followed author"
    author_list = paper.get("authors", []) or []
    authors = ", ".join(author_list[:3]) + (" et al." if len(author_list) > 3 else "")
    link = paper.get("url") or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")
    cite = f"_{paper.get('journal', '')}_ ({paper.get('published') or 'n.d.'})"
    if authors:
        cite = f"{authors} — {cite}"
    lines = [
        f"`[Followed: {who}]`",
        f"*<{link}|{_oneline(paper.get('title', ''))}>*",
        cite,
    ]
    return "\n".join(line for line in lines if line)


def _log_entry(ts, today, *, doi, title, journal, topics, source_lane,
               published, title_only=False, matched_authors=None) -> dict:
    entry = {
        "ts": ts,
        "doi": doi,
        "title": title,
        "journal": journal,
        "topics": topics,
        "posted_date": today,
        "source_lane": source_lane,
        "published": published,
        "title_only": title_only,
    }
    if matched_authors:
        entry["matched_authors"] = matched_authors
    return entry


def post_weekly_digest(
    papers_by_topic: dict[str, list[dict]],
    broader_reading: list[dict],
    followed_authors: list[dict] | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """Posts the header, then each paper and section separator as its own
    top-level message. Returns a log of what was posted, for the state
    file: [{"ts", "doi", "title", "journal", "topics", "posted_date",
    "source_lane", "published", "title_only", and "matched_authors" for
    the followed-author section}]. The extra fields feed
    track_reactions.py's per-lane / staleness / title-only /
    followed-author cuts without it re-deriving them."""
    followed_authors = followed_authors or []
    today = datetime.date.today().isoformat()
    total = (sum(len(v) for v in papers_by_topic.values())
             + len(followed_authors) + len(broader_reading))
    prefix = "[DRY RUN] " if dry_run else ""
    post_message(f"*{prefix}Weekly paper digest — {today}* ({total} papers)")

    log = []
    for topic, papers in papers_by_topic.items():
        if not papers:
            continue
        for paper in papers:
            resp = post_message(format_paper_message(paper))
            log.append(_log_entry(
                resp["ts"], today,
                doi=paper.get("doi"), title=paper["title"],
                journal=paper.get("journal", ""), topics=paper.get("topics", []),
                source_lane=paper.get("source_lane", ""),
                published=paper.get("published", ""),
                title_only=bool(paper.get("title_only")),
            ))

    if followed_authors:
        post_message("*`[Followed authors]`* — recent papers by people the group tracks")
        for paper in followed_authors:
            resp = post_message(format_followed_author_message(paper))
            log.append(_log_entry(
                resp["ts"], today,
                doi=paper.get("doi"), title=paper["title"],
                journal=paper.get("journal", ""), topics=["Followed Authors"],
                source_lane=paper.get("source_lane", "openalex_author"),
                published=paper.get("published", ""),
                matched_authors=paper.get("matched_authors", []),
            ))

    if broader_reading:
        post_message("*`[Broader Reading]`* — from Nature/Science/PNAS news & career sections")
        for item in broader_reading:
            link = item.get("url", "")
            resp = post_message(f"`[Broader Reading]`\n*<{link}|{item['title']}>*")
            log.append(_log_entry(
                resp["ts"], today,
                doi=None, title=item["title"],
                journal=item.get("source", "Broader Reading"), topics=["Broader Reading"],
                source_lane="rss", published="",
            ))

    return log
