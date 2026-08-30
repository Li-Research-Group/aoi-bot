"""
Entry point for the weekly GitHub Actions run.

Flow:
  1. Fetch candidates from RSS (fast lane) + OpenAlex journal-by-ISSN
     (backstop) + OpenAlex keyword search (broad lane)
  2. Dedupe, and drop anything already posted before (state file)
  3. Fetch followed-author candidates and pull them out of the topic pool
     -- they get their own section and bypass relevance scoring
  4. Score remaining topic candidates for relevance with Claude
  5. Group by topic, cap per topic, post to Slack as header + threaded replies
  6. Fetch the separate broader-reading feed (no relevance filtering --
     it's curated by source, not by topic match)
  7. Record run stats and update the state file with what was posted
"""

import datetime
import sys

from config import MAX_PAPERS_PER_TOPIC, BROADER_READING_FEEDS
from relevance import MODEL, filter_relevant
from sources import (
    fetch_rss_candidates,
    fetch_openalex_journal_candidates,
    fetch_openalex_candidates,
    fetch_openalex_author_candidates,
    dedupe,
    _parse_feed,
)
from stats import build_run_record
from slack_post import post_weekly_digest
from state import load_state, save_state, already_posted_keys, append_posted, append_run


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


def _key(paper: dict) -> str:
    return paper.get("doi") or paper["title"].strip().lower()


def main() -> int:
    state = load_state()
    seen_keys = already_posted_keys(state)
    today = datetime.date.today().isoformat()

    print("Fetching RSS candidates...")
    rss_papers, empty_feeds = fetch_rss_candidates()
    print(f"  {len(rss_papers)} candidates from RSS ({len(empty_feeds)} feeds returned nothing)")

    print("Fetching OpenAlex journal candidates...")
    journal_papers = fetch_openalex_journal_candidates()
    print(f"  {len(journal_papers)} candidates from OpenAlex journal scan")

    print("Fetching OpenAlex keyword candidates...")
    openalex_papers = fetch_openalex_candidates()
    print(f"  {len(openalex_papers)} candidates from OpenAlex keyword search")

    print("Fetching followed-author candidates...")
    author_papers = dedupe(fetch_openalex_author_candidates())
    print(f"  {len(author_papers)} candidates from followed authors")

    collected = {
        "rss": len(rss_papers),
        "openalex_journal": len(journal_papers),
        "openalex_keyword": len(openalex_papers),
        "openalex_author": len(author_papers),
    }

    # Order matters for dedupe (keeps the first seen): RSS first -- it carries
    # abstracts for Nature/ACS that OpenAlex sometimes lacks -- then the
    # journal lane (canonical journal name), then the broad keyword lane.
    topic_pool = rss_papers + journal_papers + openalex_papers
    deduped = dedupe(topic_pool)
    duplicates_removed = len(topic_pool) - len(deduped)

    # Followed-author papers get their own section and bypass relevance, so
    # pull them out of the topic pool before scoring -- no double-post, no
    # wasted Claude call.
    author_papers = [p for p in author_papers if _key(p) not in seen_keys]
    author_keys = {_key(p) for p in author_papers}

    new_from_topics = [p for p in deduped if _key(p) not in seen_keys]
    already_posted_removed = len(deduped) - len(new_from_topics)
    candidates = [p for p in new_from_topics if _key(p) not in author_keys]
    print(f"{len(candidates)} new topic candidates, {len(author_papers)} followed-author papers")

    # Defaults so a bail-out path still produces an honest run record.
    acct = {"scored": 0, "skipped_no_abstract": 0, "input_tokens": 0, "output_tokens": 0}
    relevant: list[dict] = []
    by_topic: dict[str, list[dict]] = {}

    if candidates:
        print("Scoring relevance with Claude...")
        relevant, acct = filter_relevant(candidates)
        print(f"  {len(relevant)} judged relevant")
        for paper in relevant:
            for topic in paper["topics"]:
                by_topic.setdefault(topic, [])
                if len(by_topic[topic]) < MAX_PAPERS_PER_TOPIC:
                    by_topic[topic].append(paper)
    else:
        print("No new topic candidates this week.")

    broader = fetch_broader_reading()

    log: list[dict] = []
    if any(by_topic.values()) or author_papers or broader:
        log = post_weekly_digest(by_topic, broader, followed_authors=author_papers)
        append_posted(state, log)
    else:
        print("Nothing to post this week.")

    run_record = build_run_record(
        date=today,
        collected=collected,
        duplicates_removed=duplicates_removed,
        already_posted_removed=already_posted_removed,
        scored=acct["scored"],
        skipped_no_abstract=acct["skipped_no_abstract"],
        relevant=len(relevant),
        posted_log=log,
        claude_input_tokens=acct["input_tokens"],
        claude_output_tokens=acct["output_tokens"],
        model=MODEL,
        empty_feeds=empty_feeds,
    )
    append_run(state, run_record)
    save_state(state)
    print(f"Posted {len(log)} messages, run recorded, state saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
