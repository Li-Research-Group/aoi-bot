"""On-demand reaction count over a chosen look-back window, posted to the
Slack channel. Run via the "Reaction count" workflow, or locally:

    python count_reactions.py                    # all logged papers
    python count_reactions.py --days 60          # last 60 days
    python count_reactions.py --days 60 --no-post  # print only

Convention (see track_reactions.py): no reaction means no strong opinion,
so the counts below are votes, not a response rate.
"""

import argparse
import datetime
import sys
import time
from collections import Counter, defaultdict

import track_reactions as tr
from state import load_state
from stats import tally_reaction_users, initials


def _fetch(ts: str) -> list[dict]:
    for attempt in range(3):
        try:
            return tr.get_message_reactions(ts)
        except RuntimeError as err:
            if "ratelimited" not in str(err) or attempt == 2:
                raise
            time.sleep(30)
    return []


def build_count(days: int | None) -> str:
    posted = load_state().get("posted", [])
    if days is not None:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        posted = [e for e in posted if e.get("posted_date", "") >= cutoff]
    if not posted:
        return "No logged papers in this window."

    by_ts: dict[str, list[dict]] = {}
    for i, e in enumerate(posted, 1):
        by_ts[e["ts"]] = _fetch(e["ts"])
        time.sleep(1.3)  # reactions.get is rate-limited (~50/min)
        if i % 25 == 0:
            print(f"  ...{i}/{len(posted)}", file=sys.stderr)

    up = down = 0
    other: Counter = Counter()
    months = defaultdict(lambda: [0, 0, 0])   # posted, up, down
    journals = defaultdict(lambda: [0, 0, 0])
    rows = []
    for e in posted:
        u, d = tr._counts(by_ts[e["ts"]])
        up += u
        down += d
        for r in by_ts[e["ts"]]:
            if r["name"] not in (tr.UPVOTE_EMOJI, tr.DOWNVOTE_EMOJI):
                other[r["name"]] += r["count"]
        for bucket in (months[e["posted_date"][:7]], journals[e.get("journal", "unknown")]):
            bucket[0] += 1
            bucket[1] += u
            bucket[2] += d
        rows.append((u - d, u, d, e["title"][:80]))

    reacted = sum(1 for e in posted if by_ts[e["ts"]])
    scope = "all logged papers" if days is None else f"last {days} days"
    L = [f"Reaction count ({scope}): {len(posted)} papers, "
         f"{posted[0]['posted_date']} .. {posted[-1]['posted_date']}",
         f"With any reaction: {reacted}   Total 👍 {up}   Total 👎 {down}",
         "Other emoji: " + (", ".join(f"{k} {v}" for k, v in other.most_common(8)) or "none"),
         "", "By month (posted / 👍 / 👎):"]
    L += [f"  {k}: {v[0]} / {v[1]} / {v[2]}" for k, v in sorted(months.items())]
    L += ["", "By journal, those with votes (posted / 👍 / 👎):"]
    L += [f"  {k}: {v[0]} / {v[1]} / {v[2]}"
          for k, v in sorted(journals.items(), key=lambda kv: -(kv[1][1] + kv[1][2])) if v[1] + v[2]]
    L += ["", "Participation (initials):"]
    users = tally_reaction_users(by_ts, tr.UPVOTE_EMOJI, tr.DOWNVOTE_EMOJI)
    L += [f"  {initials(tr.get_user_name(uid))}: {c['up']}👍 / {c['down']}👎"
          for uid, c in sorted(users.items(), key=lambda kv: -(kv[1]["up"] + kv[1]["down"]))]
    rows.sort(reverse=True)
    L += ["", "Top 10:"] + [f"  +{u}/-{d}  {t}" for _, u, d, t in rows[:10] if u or d]
    L += ["", "Bottom 10:"] + [f"  +{u}/-{d}  {t}" for _, u, d, t in rows[::-1][:10] if u or d]
    return "\n".join(L)


def _parse_days(value: str) -> int | None:
    return None if value.strip().lower() in ("", "all") else int(value)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=_parse_days, default=None,
                    help='look-back in days; omit or "all" for every logged paper')
    ap.add_argument("--no-post", action="store_true", help="print the report without posting to Slack")
    args = ap.parse_args()
    report = build_count(args.days)
    print(report)
    if not args.no_post:
        tr.post_report(report)
