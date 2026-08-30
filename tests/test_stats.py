"""Tests for stats.py -- the pure aggregation logic behind the weekly run
record and the monthly report. No network, no Slack: everything here takes
plain dicts in and returns plain dicts out."""

from stats import (
    estimate_cost_usd,
    build_run_record,
    summarize_runs,
    posted_stats,
    tally_reaction_users,
    followed_author_stats,
)


# --- estimate_cost_usd -------------------------------------------------

def test_estimate_cost_uses_per_million_pricing():
    # claude-sonnet-4-6 is $3.00 / 1M input, $15.00 / 1M output
    cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 100_000)
    assert cost == 4.5  # 3.00 + (0.1 * 15.00)


def test_estimate_cost_unknown_model_returns_none():
    assert estimate_cost_usd("mystery-model-9", 1000, 1000) is None


# --- build_run_record ------------------------------------------------

def _posted_log():
    return [
        {"ts": "1", "source_lane": "rss", "topics": ["A"],
         "published": "2026-08-01", "posted_date": "2026-08-30"},
        {"ts": "2", "source_lane": "openalex_journal", "topics": ["A"],
         "published": "", "posted_date": "2026-08-30"},
        {"ts": "3", "source_lane": "rss", "topics": ["B"],
         "published": "2026-08-02", "posted_date": "2026-08-30"},
    ]


def test_build_run_record_derives_duplicates_lanes_and_cost():
    rec = build_run_record(
        date="2026-08-30",
        collected={"rss": 40, "openalex_journal": 100, "openalex_keyword": 30},
        duplicates_removed=50,
        already_posted_removed=10,
        scored=110,
        skipped_no_abstract=20,
        relevant=8,
        posted_log=_posted_log(),
        claude_input_tokens=500_000,
        claude_output_tokens=20_000,
        model="claude-sonnet-4-6",
        empty_feeds=["Green Chemistry"],
    )
    assert rec["date"] == "2026-08-30"
    assert rec["collected"] == {"rss": 40, "openalex_journal": 100, "openalex_keyword": 30}
    assert rec["duplicates_removed"] == 50
    assert rec["already_posted_removed"] == 10
    assert rec["scored"] == 110
    assert rec["skipped_no_abstract"] == 20
    assert rec["relevant"] == 8
    assert rec["posted"] == 3
    assert rec["posted_by_lane"] == {"rss": 2, "openalex_journal": 1}
    # 0.5M * $3 + 0.02M * $15 = 1.5 + 0.3
    assert rec["claude_cost_usd"] == 1.8
    assert rec["claude_input_tokens"] == 500_000
    assert rec["claude_output_tokens"] == 20_000
    assert rec["empty_feeds"] == ["Green Chemistry"]


# --- summarize_runs ------------------------------------------------

def _runs():
    return [
        {"date": "2026-06-20", "collected": {"rss": 1, "openalex_journal": 1, "openalex_keyword": 1},
         "duplicates_removed": 0, "already_posted_removed": 0, "scored": 3, "skipped_no_abstract": 0,
         "relevant": 1, "posted": 1, "posted_by_lane": {"rss": 1},
         "claude_cost_usd": 0.1, "empty_feeds": ["Green Chemistry"]},
        {"date": "2026-07-15", "collected": {"rss": 10, "openalex_journal": 20, "openalex_keyword": 5},
         "duplicates_removed": 5, "already_posted_removed": 2, "scored": 28, "skipped_no_abstract": 3,
         "relevant": 6, "posted": 4, "posted_by_lane": {"rss": 3, "openalex_journal": 1},
         "claude_cost_usd": 0.5, "empty_feeds": ["Green Chemistry"]},
        {"date": "2026-08-01", "collected": {"rss": 12, "openalex_journal": 18, "openalex_keyword": 6},
         "duplicates_removed": 6, "already_posted_removed": 3, "scored": 27, "skipped_no_abstract": 4,
         "relevant": 5, "posted": 3, "posted_by_lane": {"rss": 2, "openalex_keyword": 1},
         "claude_cost_usd": 0.7, "empty_feeds": ["Green Chemistry", "ACS Environmental Au"]},
    ]


def test_summarize_runs_windows_by_date():
    summary = summarize_runs(_runs(), since="2026-07-01")
    assert summary["n_runs"] == 2  # the June run is excluded


def test_summarize_runs_aggregates_funnel():
    summary = summarize_runs(_runs(), since="2026-07-01")
    assert summary["collected_total"] == (10 + 20 + 5) + (12 + 18 + 6)  # 71
    assert summary["relevant_total"] == 11
    assert summary["posted_total"] == 7
    assert summary["posted_by_lane"] == {"rss": 5, "openalex_journal": 1, "openalex_keyword": 1}
    assert summary["avg_cost_usd"] == 0.6  # (0.5 + 0.7) / 2


def test_summarize_runs_flags_feeds_empty_in_every_windowed_run():
    summary = summarize_runs(_runs(), since="2026-07-01")
    # Green Chemistry is empty in both July and August runs; ACS Environmental
    # Au only in one -- so only Green Chemistry is "always empty".
    assert summary["always_empty_feeds"] == ["Green Chemistry"]


# --- posted_stats ------------------------------------------------

def _posted():
    return [
        {"ts": "1", "topics": ["Water"], "title_only": False,
         "published": "2026-08-01", "posted_date": "2026-08-10",
         "journal": "ES&T", "title": "P1"},
        {"ts": "2", "topics": ["Water", "Cross"], "title_only": True,
         "published": "2026-08-05", "posted_date": "2026-08-10",
         "journal": "Water Research", "title": "P2"},
        {"ts": "3", "topics": ["Cross"], "title_only": False,
         "published": "", "posted_date": "2026-08-10",
         "journal": "Nature", "title": "P3"},
    ]


def test_posted_stats_counts_tags_and_engagement():
    reactions = {"1": (3, 0), "2": (0, 0), "3": (1, 2)}
    s = posted_stats(_posted(), reactions, since="2026-08-01")
    assert s["n_posted"] == 3
    assert s["by_tag"] == {"Water": 2, "Cross": 2}
    # P1 and P3 have reactions, P2 has none -> 2/3
    assert s["engagement_rate"] == round(2 / 3, 4)


def test_posted_stats_splits_title_only_from_abstract_cohort():
    reactions = {"1": (3, 0), "2": (0, 0), "3": (1, 2)}
    s = posted_stats(_posted(), reactions, since="2026-08-01")
    assert s["title_only"]["n"] == 1
    assert s["title_only"]["upvote_rate"] is None  # no votes on P2
    assert s["with_abstract"]["n"] == 2
    assert s["with_abstract"]["upvote_rate"] == round(4 / 6, 4)  # up 4, down 2


def test_initials_reduces_names_to_letters():
    from stats import initials
    assert initials("Zoe Li") == "ZL"
    assert initials("zoe.yalin.li") == "ZYL"
    assert initials("Zoe") == "Z"
    assert initials("   ") == "?"


def test_followed_author_stats_groups_by_matched_author():
    posted = [
        {"ts": "a", "source_lane": "openalex_author", "matched_authors": ["Jane Smith"],
         "posted_date": "2026-08-10", "title": "P1"},
        {"ts": "b", "source_lane": "openalex_author", "matched_authors": ["Jane Smith"],
         "posted_date": "2026-08-11", "title": "P2"},
        {"ts": "c", "source_lane": "openalex_author", "matched_authors": ["Bob Lee"],
         "posted_date": "2026-08-12", "title": "P3"},
        {"ts": "d", "source_lane": "rss", "topics": ["X"],
         "posted_date": "2026-08-12", "title": "not an author paper"},
    ]
    reactions = {"a": (3, 0), "b": (0, 1), "c": (0, 0), "d": (5, 5)}
    s = followed_author_stats(posted, reactions, since="2026-08-01")

    assert set(s) == {"Jane Smith", "Bob Lee"}
    assert s["Jane Smith"]["n"] == 2
    assert s["Jane Smith"]["upvote_rate"] == round(3 / 4, 4)  # up 3, down 1
    assert s["Bob Lee"]["n"] == 1
    assert s["Bob Lee"]["upvote_rate"] is None  # no votes


def test_tally_reaction_users_counts_up_and_down_per_user():
    data = {
        "1": [{"name": "thumbsup", "users": ["U1", "U2"]},
              {"name": "thumbsdown", "users": ["U3"]}],
        "2": [{"name": "thumbsup", "users": ["U1"]},
              {"name": "eyes", "users": ["U9"]}],  # untracked emoji -> ignored
    }
    t = tally_reaction_users(data, "thumbsup", "thumbsdown")
    assert t == {
        "U1": {"up": 2, "down": 0},
        "U2": {"up": 1, "down": 0},
        "U3": {"up": 0, "down": 1},
    }


def test_posted_stats_median_staleness_ignores_undated():
    reactions = {"1": (0, 0), "2": (0, 0), "3": (0, 0)}
    s = posted_stats(_posted(), reactions, since="2026-08-01")
    # P1: 2026-08-01 -> 2026-08-10 = 9 days; P2: 5 days; P3: undated, skipped
    assert s["median_staleness_days"] == 7.0
