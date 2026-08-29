"""
Monthly job: reads every paper posted in the last ~30 days from the state
file, pulls its Slack reaction counts, and posts a simple leaderboard --
which journals/topics are getting upvoted vs. downvoted -- so the group
can decide whether to drop a journal, add an author-specific search, or
otherwise adjust the config. This is intentionally a report for a human
to act on, not an auto-adjusting system: a few stray downvotes shouldn't
silently drop a journal from the pipeline.

Convention: react with 👍 (thumbsup) for "worth tracking this
journal/topic" and 👎 (thumbsdown) for "not useful" on any paper message.
"""

import datetime
import os
from collections import defaultdict

import requests

from config import SLACK_CHANNEL_ID
from state import load_state

SLACK_API = "https://slack.com/api"
LOOKBACK_DAYS = 30
UPVOTE_EMOJI = "thumbsup"
DOWNVOTE_EMOJI = "thumbsdown"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}


def get_reactions(message_ts: str) -> tuple[int, int]:
    resp = requests.get(
        f"{SLACK_API}/reactions.get",
        headers=_headers(),
        params={"channel": SLACK_CHANNEL_ID, "timestamp": message_ts},
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        # Message may have no reactions at all -- Slack returns an error
        # for that case rather than an empty list.
        return (0, 0)
    reactions = data.get("message", {}).get("reactions", [])
    up = next((r["count"] for r in reactions if r["name"] == UPVOTE_EMOJI), 0)
    down = next((r["count"] for r in reactions if r["name"] == DOWNVOTE_EMOJI), 0)
    return (up, down)


def build_report() -> str:
    state = load_state()
    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()

    by_journal = defaultdict(lambda: {"up": 0, "down": 0, "n": 0})
    by_topic = defaultdict(lambda: {"up": 0, "down": 0, "n": 0})

    for entry in state["posted"]:
        if entry.get("posted_date", "") < cutoff:
            continue
        up, down = get_reactions(entry["ts"])
        journal = entry.get("journal", "unknown")
        by_journal[journal]["up"] += up
        by_journal[journal]["down"] += down
        by_journal[journal]["n"] += 1
        for topic in entry.get("topics", []):
            by_topic[topic]["up"] += up
            by_topic[topic]["down"] += down
            by_topic[topic]["n"] += 1

    lines = [f"*Monthly aoi-bot report* (last {LOOKBACK_DAYS} days)", "", "*By journal:*"]
    for journal, counts in sorted(by_journal.items(), key=lambda kv: -kv[1]["up"] + kv[1]["down"]):
        total_votes = counts["up"] + counts["down"]
        rate = f"{100 * counts['up'] / total_votes:.0f}% upvoted" if total_votes else "no votes yet"
        lines.append(f"  - {journal}: {counts['n']} papers posted, {rate}")

    lines.append("")
    lines.append("*By topic:*")
    for topic, counts in sorted(by_topic.items(), key=lambda kv: -kv[1]["up"] + kv[1]["down"]):
        total_votes = counts["up"] + counts["down"]
        rate = f"{100 * counts['up'] / total_votes:.0f}% upvoted" if total_votes else "no votes yet"
        lines.append(f"  - {topic}: {counts['n']} papers posted, {rate}")

    lines.append("")
    lines.append("_React 👍/👎 on individual papers to feed next month's report. Low-scoring journals/topics are candidates to drop or narrow; consistently upvoted authors are candidates for a dedicated author-tracking query._")
    return "\n".join(lines)


def post_report(report: str) -> None:
    resp = requests.post(
        f"{SLACK_API}/chat.postMessage",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"channel": SLACK_CHANNEL_ID, "text": report},
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack post failed: {data}")


if __name__ == "__main__":
    report = build_report()
    print(report)
    post_report(report)
