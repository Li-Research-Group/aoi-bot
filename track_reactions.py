"""Monthly job: reads the last ~30 days of pipeline activity from the
state file and posts a report to Slack so the group can tune the config.

Two data sources feed the report:
  - state["runs"] -- one stats record per weekly run (funnel, per-lane
    counts, Claude cost, dead feeds). Written by run_weekly.py.
  - state["posted"] + live Slack reaction counts -- per-tag volume,
    engagement, the title-only vs abstract cohort, staleness, and the
    per-journal / per-topic 👍 rates.

This is intentionally a report for a human to act on, not an
auto-adjusting system: a few stray downvotes shouldn't silently drop a
journal from the pipeline.

Convention: react with 👍 (thumbsup) for "worth tracking this
journal/topic" and 👎 (thumbsdown) for "not useful" on any paper message.
"""

import datetime
import os
from collections import defaultdict

import requests

from config import SLACK_CHANNEL_ID
from stats import (
    summarize_runs,
    posted_stats,
    tally_reaction_users,
    followed_author_stats,
    initials,
)
from state import load_state

SLACK_API = "https://slack.com/api"
LOOKBACK_DAYS = 30
UPVOTE_EMOJI = "thumbsup"
DOWNVOTE_EMOJI = "thumbsdown"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}


def get_message_reactions(message_ts: str) -> list[dict]:
    """Raw `reactions` array for one message: [{"name", "count", "users"}].
    Empty list if the message has no reactions (Slack returns an error for
    that case rather than an empty list)."""
    resp = requests.get(
        f"{SLACK_API}/reactions.get",
        headers=_headers(),
        params={"channel": SLACK_CHANNEL_ID, "timestamp": message_ts, "full": "true"},
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        return []
    return data.get("message", {}).get("reactions", [])


def _counts(reactions: list[dict]) -> tuple[int, int]:
    up = next((r["count"] for r in reactions if r["name"] == UPVOTE_EMOJI), 0)
    down = next((r["count"] for r in reactions if r["name"] == DOWNVOTE_EMOJI), 0)
    return (up, down)


_USER_NAMES: dict[str, str] = {}


def get_user_name(user_id: str) -> str:
    if user_id in _USER_NAMES:
        return _USER_NAMES[user_id]
    try:
        resp = requests.get(
            f"{SLACK_API}/users.info",
            headers=_headers(),
            params={"user": user_id},
            timeout=15,
        )
        data = resp.json()
        profile = data.get("user", {}).get("profile", {}) if data.get("ok") else {}
        name = profile.get("display_name") or data.get("user", {}).get("real_name") or user_id
    except Exception:  # noqa: BLE001 -- a name lookup shouldn't sink the report
        name = user_id
    _USER_NAMES[user_id] = name
    return name


def _pct(rate: float | None) -> str:
    return "n/a" if rate is None else f"{100 * rate:.0f}%"


def _n_papers(n: int) -> str:
    return f"{n} paper" if n == 1 else f"{n} papers"


def build_report() -> str:
    state = load_state()
    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()

    windowed = [e for e in state.get("posted", []) if e.get("posted_date", "") >= cutoff]

    # One Slack call per posted message; derive both the up/down counts and
    # the per-user lists from the same response.
    counts: dict[str, tuple[int, int]] = {}
    reaction_users: dict[str, list[dict]] = {}
    for entry in windowed:
        reactions = get_message_reactions(entry["ts"])
        counts[entry["ts"]] = _counts(reactions)
        reaction_users[entry["ts"]] = reactions

    pipeline = summarize_runs(state.get("runs", []), since=cutoff)
    posted = posted_stats(state.get("posted", []), counts, since=cutoff)
    authors = followed_author_stats(state.get("posted", []), counts, since=cutoff)
    users = tally_reaction_users(reaction_users, UPVOTE_EMOJI, DOWNVOTE_EMOJI)

    L: list[str] = [f"*Monthly aoi-bot report* (last {LOOKBACK_DAYS} days)"]

    # --- Pipeline -----------------------------------------------------
    L += ["", "*Pipeline*"]
    if pipeline.get("n_runs", 0) == 0:
        L.append("  - no runs recorded yet this window")
    else:
        L.append(
            f"  - {pipeline['n_runs']} runs: "
            f"{pipeline['collected_total']} collected → "
            f"{pipeline['scored_total']} scored → "
            f"{pipeline['relevant_total']} relevant ({_pct(pipeline['relevant_yield'])}) → "
            f"{pipeline['posted_total']} posted"
        )
        L.append(f"  - duplicates removed across lanes: {pipeline['duplicates_removed_total']}")
        lane = pipeline.get("posted_by_lane", {})
        if lane:
            L.append("  - posted by lane: " + ", ".join(f"{k} {v}" for k, v in sorted(lane.items())))
        if pipeline.get("avg_cost_usd") is not None:
            L.append(f"  - avg Claude cost/run: ${pipeline['avg_cost_usd']:.2f}")
        if pipeline.get("always_empty_feeds"):
            L.append("  - ⚠️ feeds empty every run (check for breakage): "
                     + ", ".join(pipeline["always_empty_feeds"]))

    # --- Posted papers ---------------------------------------------
    L += ["", "*Posted papers*"]
    L.append(f"  - {posted['n_posted']} posted, {_pct(posted['engagement_rate'])} got at least one reaction")
    if posted.get("median_staleness_days") is not None:
        L.append(f"  - median lag (published → posted): {posted['median_staleness_days']:.0f} days")
    ta = posted["with_abstract"]
    to = posted["title_only"]
    L.append(f"  - abstract-scored: {_n_papers(ta['n'])}, {_pct(ta['upvote_rate'])} upvoted")
    L.append(f"  - title-only (Elsevier): {_n_papers(to['n'])}, {_pct(to['upvote_rate'])} upvoted")
    if posted.get("by_tag"):
        L.append("  - by tag: " + ", ".join(
            f"{tag} {n}" for tag, n in sorted(posted["by_tag"].items(), key=lambda kv: -kv[1])
        ))
    if posted.get("top"):
        L.append("  - most upvoted:")
        for p in posted["top"]:
            if p["up"] > p["down"]:
                L.append(f"      +{p['up']}/-{p['down']}  {p['title'][:80]}")
    if posted.get("bottom"):
        downvoted = [p for p in posted["bottom"] if p["down"] > p["up"]]
        if downvoted:
            L.append("  - net downvoted:")
            for p in downvoted:
                L.append(f"      +{p['up']}/-{p['down']}  {p['title'][:80]}")

    # --- By journal / topic (👍 rate) --------------------------------
    by_journal = defaultdict(lambda: {"up": 0, "down": 0, "n": 0})
    by_topic = defaultdict(lambda: {"up": 0, "down": 0, "n": 0})
    for entry in windowed:
        up, down = counts.get(entry["ts"], (0, 0))
        j = by_journal[entry.get("journal", "unknown")]
        j["up"] += up
        j["down"] += down
        j["n"] += 1
        for topic in entry.get("topics", []):
            t = by_topic[topic]
            t["up"] += up
            t["down"] += down
            t["n"] += 1

    def _rate_lines(d: dict) -> list[str]:
        rows = []
        for name, c in sorted(d.items(), key=lambda kv: kv[1]["down"] - kv[1]["up"], reverse=True):
            votes = c["up"] + c["down"]
            rate = f"{100 * c['up'] / votes:.0f}% upvoted" if votes else "no votes yet"
            rows.append(f"  - {name}: {c['n']} posted, {rate}")
        return rows

    L += ["", "*By journal:*"] + _rate_lines(by_journal)
    L += ["", "*By topic:*"] + _rate_lines(by_topic)

    # --- Followed authors ----------------------------------------
    if authors:
        L += ["", "*Followed authors* (own lane, bypasses relevance)"]
        for name, c in sorted(authors.items(), key=lambda kv: -kv[1]["n"]):
            rate = "no votes yet" if c["upvote_rate"] is None else f"{_pct(c['upvote_rate'])} upvoted"
            L.append(f"  - {name}: {_n_papers(c['n'])}, {rate}")

    # --- Participation ---------------------------------------------
    if users:
        L += ["", "*Participation* (reactions given, by initials -- not a scoreboard)"]
        for uid, c in sorted(users.items(), key=lambda kv: -(kv[1]["up"] + kv[1]["down"])):
            L.append(f"  - {initials(get_user_name(uid))}: {c['up'] + c['down']} reactions ({c['up']}👍 / {c['down']}👎)")

    L += ["", "_React 👍/👎 on individual papers to feed next month's report. "
          "Low-scoring journals/topics are candidates to drop or narrow; "
          "consistently upvoted authors are candidates for a dedicated author-tracking query._"]
    return "\n".join(L)


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
