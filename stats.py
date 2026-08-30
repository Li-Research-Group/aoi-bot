"""Pure aggregation logic for the pipeline stats.

Two consumers:
  - run_weekly.py calls build_run_record() once per run and appends the
    result to state["runs"].
  - track_reactions.py calls summarize_runs() and posted_stats() to build
    the monthly report.

Everything here takes plain dicts and returns plain dicts -- no network,
no Slack, no file IO -- so it can be tested directly (see test_stats.py).
"""

import re
from collections import Counter
from statistics import median

# USD per 1,000,000 tokens, as (input, output). Keep in sync with the
# model set in relevance.py. An unknown model -> cost reported as None
# rather than a wrong number.
MODEL_PRICING = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = MODEL_PRICING.get(model)
    if price is None:
        return None
    in_price, out_price = price
    cost = input_tokens / 1e6 * in_price + output_tokens / 1e6 * out_price
    return round(cost, 4)


def _lane_counts(posted_log: list[dict]) -> dict:
    counts = Counter(e.get("source_lane", "unknown") for e in posted_log)
    return dict(counts)


def build_run_record(
    *,
    date: str,
    collected: dict,
    after_dedupe: int,
    already_posted_removed: int,
    scored: int,
    skipped_no_abstract: int,
    relevant: int,
    posted_log: list[dict],
    claude_input_tokens: int,
    claude_output_tokens: int,
    model: str,
    empty_feeds: list[str],
) -> dict:
    """Assemble one run's stats record for state["runs"]."""
    collected_total = sum(collected.values())
    return {
        "date": date,
        "collected": dict(collected),
        "duplicates_removed": collected_total - after_dedupe,
        "already_posted_removed": already_posted_removed,
        "scored": scored,
        "skipped_no_abstract": skipped_no_abstract,
        "relevant": relevant,
        "posted": len(posted_log),
        "posted_by_lane": _lane_counts(posted_log),
        "claude_input_tokens": claude_input_tokens,
        "claude_output_tokens": claude_output_tokens,
        "claude_cost_usd": estimate_cost_usd(model, claude_input_tokens, claude_output_tokens),
        "empty_feeds": list(empty_feeds),
    }


def summarize_runs(runs: list[dict], since: str) -> dict:
    """Roll up every run on or after `since` (an ISO date string) into the
    pipeline section of the monthly report."""
    windowed = [r for r in runs if r.get("date", "") >= since]
    if not windowed:
        return {"n_runs": 0}

    collected_total = sum(sum(r.get("collected", {}).values()) for r in windowed)
    scored_total = sum(r.get("scored", 0) for r in windowed)
    relevant_total = sum(r.get("relevant", 0) for r in windowed)
    posted_total = sum(r.get("posted", 0) for r in windowed)
    dup_total = sum(r.get("duplicates_removed", 0) for r in windowed)

    by_lane: Counter = Counter()
    for r in windowed:
        by_lane.update(r.get("posted_by_lane", {}))

    costs = [r["claude_cost_usd"] for r in windowed if r.get("claude_cost_usd") is not None]

    # A feed counts as "always empty" only if it shows up in the empty list
    # of every run in the window -- one good fetch clears it.
    empty_sets = [set(r.get("empty_feeds", [])) for r in windowed]
    always_empty = set.intersection(*empty_sets) if empty_sets else set()

    return {
        "n_runs": len(windowed),
        "collected_total": collected_total,
        "scored_total": scored_total,
        "relevant_total": relevant_total,
        "posted_total": posted_total,
        "duplicates_removed_total": dup_total,
        "relevant_yield": round(relevant_total / scored_total, 4) if scored_total else None,
        "posted_yield": round(posted_total / collected_total, 4) if collected_total else None,
        "posted_by_lane": dict(by_lane),
        "avg_cost_usd": round(sum(costs) / len(costs), 4) if costs else None,
        "always_empty_feeds": sorted(always_empty),
    }


def initials(name: str) -> str:
    """Reduce a display name to up to three uppercase initials, so the
    monthly report's participation section names no one outright.
    'Zoe Li' -> 'ZL', 'zoe.yalin.li' -> 'ZYL'."""
    parts = [p for p in re.split(r"[\s._\-]+", name.strip()) if p]
    letters = "".join(p[0] for p in parts if p[0].isalpha())
    return letters[:3].upper() or "?"


def tally_reaction_users(reaction_users_by_ts: dict, up_emoji: str, down_emoji: str) -> dict:
    """Given {ts: [{"name": emoji, "users": [uid, ...]}, ...]} (the shape
    Slack's reactions.get returns), tally 👍/👎 given per user. Only the
    two tracked emoji count; anything else is ignored. This is a
    participation view, not a scoreboard -- see track_reactions.py."""
    out: dict = {}
    for reactions in reaction_users_by_ts.values():
        for r in reactions:
            if r.get("name") == up_emoji:
                key = "up"
            elif r.get("name") == down_emoji:
                key = "down"
            else:
                continue
            for uid in r.get("users", []):
                out.setdefault(uid, {"up": 0, "down": 0})[key] += 1
    return out


def _days_between(earlier: str, later: str) -> int | None:
    import datetime
    try:
        d0 = datetime.date.fromisoformat(earlier)
        d1 = datetime.date.fromisoformat(later)
    except (ValueError, TypeError):
        return None
    return (d1 - d0).days


def _cohort(entries: list[dict], reactions: dict) -> dict:
    up = sum(reactions.get(e["ts"], (0, 0))[0] for e in entries)
    down = sum(reactions.get(e["ts"], (0, 0))[1] for e in entries)
    total = up + down
    return {
        "n": len(entries),
        "up": up,
        "down": down,
        "upvote_rate": round(up / total, 4) if total else None,
    }


def posted_stats(posted: list[dict], reactions: dict, since: str) -> dict:
    """Build the 'posted papers' section: per-tag counts, engagement,
    title-only vs abstract cohorts, staleness, per-paper reaction extremes.

    `reactions` maps message ts -> (up, down).
    """
    entries = [e for e in posted if e.get("posted_date", "") >= since]

    by_tag: Counter = Counter()
    for e in entries:
        by_tag.update(e.get("topics", []))

    with_reaction = sum(
        1 for e in entries if sum(reactions.get(e["ts"], (0, 0))) > 0
    )

    staleness = [
        d for e in entries
        if (d := _days_between(e.get("published", ""), e.get("posted_date", ""))) is not None
    ]

    per_paper = []
    for e in entries:
        u, d = reactions.get(e["ts"], (0, 0))
        if u or d:
            per_paper.append({"title": e.get("title", ""), "journal": e.get("journal", ""),
                              "up": u, "down": d, "net": u - d})
    per_paper.sort(key=lambda p: p["net"])

    return {
        "n_posted": len(entries),
        "by_tag": dict(by_tag),
        "engagement_rate": round(with_reaction / len(entries), 4) if entries else None,
        "title_only": _cohort([e for e in entries if e.get("title_only")], reactions),
        "with_abstract": _cohort([e for e in entries if not e.get("title_only")], reactions),
        "median_staleness_days": median(staleness) if staleness else None,
        "bottom": per_paper[:5],
        "top": list(reversed(per_paper[-5:])),
    }
