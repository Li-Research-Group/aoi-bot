"""
Posts the weekly digest to Slack: one header message, then each paper as
a threaded reply underneath it. Threading matters because the reaction
tracker (track_reactions.py) needs a distinct message per paper to attach
a per-paper thumbs-up/down count to.
"""

import datetime
import os

import requests

from config import SLACK_CHANNEL_ID

SLACK_API = "https://slack.com/api"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}", "Content-Type": "application/json"}


def post_message(text: str, thread_ts: str | None = None) -> dict:
    payload = {"channel": SLACK_CHANNEL_ID, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
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


def post_weekly_digest(papers_by_topic: dict[str, list[dict]], broader_reading: list[dict]) -> list[dict]:
    """Posts the header + threaded papers. Returns a log of what was
    posted, for the state file: [{"ts", "doi", "title", "journal",
    "topics", "posted_date", "source_lane", "published", "title_only"}].
    The last three feed track_reactions.py's per-lane / staleness /
    title-only-cohort cuts without it having to re-derive them."""
    today = datetime.date.today().isoformat()
    total = sum(len(v) for v in papers_by_topic.values()) + len(broader_reading)
    header = post_message(f"*Weekly paper digest — {today}* ({total} papers)")
    thread_ts = header["ts"]

    log = []
    for topic, papers in papers_by_topic.items():
        if not papers:
            continue
        for paper in papers:
            resp = post_message(format_paper_message(paper), thread_ts=thread_ts)
            log.append(
                {
                    "ts": resp["ts"],
                    "doi": paper.get("doi"),
                    "title": paper["title"],
                    "journal": paper.get("journal", ""),
                    "topics": paper.get("topics", []),
                    "posted_date": today,
                    "source_lane": paper.get("source_lane", ""),
                    "published": paper.get("published", ""),
                    "title_only": bool(paper.get("title_only")),
                }
            )

    if broader_reading:
        post_message("*`[Broader Reading]`* — from Nature/Science/PNAS news & career sections", thread_ts=thread_ts)
        for item in broader_reading:
            link = item.get("url", "")
            resp = post_message(f"`[Broader Reading]`\n*<{link}|{item['title']}>*", thread_ts=thread_ts)
            log.append(
                {
                    "ts": resp["ts"],
                    "doi": None,
                    "title": item["title"],
                    "journal": item.get("source", "Broader Reading"),
                    "topics": ["Broader Reading"],
                    "posted_date": today,
                    "source_lane": "rss",
                    "published": "",
                    "title_only": False,
                }
            )

    return log
