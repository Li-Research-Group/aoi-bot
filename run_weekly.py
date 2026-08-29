"""
Entry point for the weekly GitHub Actions run.

Flow:
  1. Fetch candidates from RSS (fast lane) + OpenAlex (broad lane)
  2. Dedupe, and drop anything already posted before (state file)
  3. Score remaining candidates for relevance with Claude
  4. Group by topic, cap per topic, post to Slack as header + threaded replies
  5. Fetch the separate broader-reading feed (no relevance filtering --
     it's curated by source, not by topic match)
  6. Update the state file with what was posted this run
"""

import sys

from config import MAX_PAPERS_PER_TOPIC, BROADER_READING_FEEDS
from sources import fetch_rss_candidates, fetch_openalex_candidates, dedupe, _parse_feed
from relevance import filter_relevant
from slack_post import post_weekly_digest
from state import load_state, save_state, already_posted_keys, append_posted


def fetch_broader_reading() -> list[dict]:
    items = []
    for source_name, feed_url in BROADER_READING_FEEDS.items():
        if not feed_url or feed_url.startswith("FILL_IN"):
            continue
        try:
            entries = _parse_feed(feed_url)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] failed to fetch broader-reading feed {source_name}: {exc}")
            continue
        # Broader reading: just take the most recent 2-3 items per source,
        # no relevance filtering -- these are curated by being in a
        # News/Career/Comment feed at all.
        for entry in entries[:3]:
            items.append({"title": entry["title"], "url": entry["url"], "source": source_name})
    return items


def main() -> int:
    state = load_state()
    seen_keys = already_posted_keys(state)

    print("Fetching RSS candidates...")
    rss_papers = fetch_rss_candidates()
    print(f"  {len(rss_papers)} candidates from RSS")

    print("Fetching OpenAlex candidates...")
    openalex_papers = fetch_openalex_candidates()
    print(f"  {len(openalex_papers)} candidates from OpenAlex")

    candidates = dedupe(rss_papers + openalex_papers)
    candidates = [
        p for p in candidates
        if (p.get("doi") or p["title"].strip().lower()) not in seen_keys
    ]
    print(f"{len(candidates)} new candidates after dedupe + already-posted filter")

    if not candidates:
        print("Nothing new this week.")
        broader = fetch_broader_reading()
        if broader:
            log = post_weekly_digest({}, broader)
            append_posted(state, log)
            save_state(state)
        return 0

    print("Scoring relevance with Claude...")
    relevant = filter_relevant(candidates)
    print(f"  {len(relevant)} judged relevant")

    # Group by topic, respecting the per-topic cap
    by_topic: dict[str, list[dict]] = {}
    for paper in relevant:
        for topic in paper["topics"]:
            by_topic.setdefault(topic, [])
            if len(by_topic[topic]) < MAX_PAPERS_PER_TOPIC:
                by_topic[topic].append(paper)

    broader = fetch_broader_reading()

    if not any(by_topic.values()) and not broader:
        print("Nothing to post after filtering.")
        return 0

    log = post_weekly_digest(by_topic, broader)
    append_posted(state, log)
    save_state(state)
    print(f"Posted {len(log)} messages, state saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
