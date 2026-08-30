"""Integration test for run_weekly.main(): with the network lanes and the
Slack post stubbed out, one full pass must leave a stats record in
state["runs"] carrying the funnel numbers, the dead feed, and the Claude
token usage."""

import run_weekly


def _stub_pipeline(monkeypatch, *, rss, empty_feeds, relevant, acct, log, authors=()):
    monkeypatch.setattr(run_weekly, "fetch_rss_candidates", lambda: (rss, empty_feeds))
    monkeypatch.setattr(run_weekly, "fetch_openalex_journal_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_author_candidates", lambda: list(authors))
    monkeypatch.setattr(run_weekly, "fetch_broader_reading", lambda: [])
    monkeypatch.setattr(run_weekly, "filter_relevant", lambda candidates: (relevant, acct))
    monkeypatch.setattr(run_weekly, "post_weekly_digest",
                        lambda by_topic, broader, followed_authors=None, dry_run=False: log)


def test_main_records_a_run_with_funnel_and_dead_feed(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_weekly, "load_state", lambda: {"posted": [], "runs": []})
    monkeypatch.setattr(run_weekly, "save_state", lambda s: captured.update(s))

    rss = [{"title": "A paper", "doi": "10.1/a", "abstract": "x",
            "source_lane": "rss", "published": "2026-08-01"}]
    relevant = [{**rss[0], "topics": ["Water/Wastewater Treatment (teaching)"], "title_only": False}]
    acct = {"scored": 1, "skipped_no_abstract": 3, "input_tokens": 1200, "output_tokens": 90}
    log = [{"ts": "111.1", "source_lane": "rss", "topics": ["Water/Wastewater Treatment (teaching)"],
            "published": "2026-08-01", "posted_date": "2026-08-30"}]
    _stub_pipeline(monkeypatch, rss=rss, empty_feeds=["Green Chemistry"],
                   relevant=relevant, acct=acct, log=log)

    assert run_weekly.main() == 0

    runs = captured["runs"]
    assert len(runs) == 1
    rec = runs[0]
    assert rec["collected"] == {"rss": 1, "openalex_journal": 0,
                                "openalex_keyword": 0, "openalex_author": 0}
    assert rec["scored"] == 1
    assert rec["skipped_no_abstract"] == 3
    assert rec["relevant"] == 1
    assert rec["posted"] == 1
    assert rec["posted_by_lane"] == {"rss": 1}
    assert rec["claude_input_tokens"] == 1200
    assert rec["claude_cost_usd"] is not None
    assert rec["empty_feeds"] == ["Green Chemistry"]


def test_main_still_records_a_run_on_a_quiet_week(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_weekly, "load_state", lambda: {"posted": [], "runs": []})
    monkeypatch.setattr(run_weekly, "save_state", lambda s: captured.update(s))
    _stub_pipeline(monkeypatch, rss=[], empty_feeds=["Green Chemistry", "Energy & Environmental Science"],
                   relevant=[], acct={"scored": 0, "skipped_no_abstract": 0,
                                      "input_tokens": 0, "output_tokens": 0}, log=[])

    assert run_weekly.main() == 0
    runs = captured["runs"]
    assert len(runs) == 1
    assert runs[0]["posted"] == 0
    assert runs[0]["empty_feeds"] == ["Green Chemistry", "Energy & Environmental Science"]


def test_dry_run_uses_the_heuristic_and_never_calls_claude(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_weekly, "load_state", lambda: {"posted": [], "runs": []})
    monkeypatch.setattr(run_weekly, "save_state", lambda s: captured.update(s))
    monkeypatch.setattr(run_weekly, "DRY_RUN", True)

    def boom(*a, **k):
        raise AssertionError("filter_relevant must not be called in a dry run")

    monkeypatch.setattr(run_weekly, "filter_relevant", boom)

    heuristic_calls = []

    def fake_heuristic(candidates):
        heuristic_calls.append(len(candidates))
        return ([{**candidates[0], "topics": ["T"], "title_only": False}],
                {"scored": 1, "skipped_no_abstract": 0, "input_tokens": 0, "output_tokens": 0})

    monkeypatch.setattr(run_weekly, "heuristic_filter", fake_heuristic)

    dry_run_flags = []

    def fake_post(by_topic, broader, followed_authors=None, dry_run=False):
        dry_run_flags.append(dry_run)
        return [{"ts": "1", "source_lane": "rss", "topics": ["T"],
                 "published": "2026-08-01", "posted_date": "2026-08-30", "title_only": False}]

    rss = [{"title": "P", "doi": "10.1/p", "abstract": "x",
            "source_lane": "rss", "published": "2026-08-01"}]
    monkeypatch.setattr(run_weekly, "fetch_rss_candidates", lambda: (rss, []))
    monkeypatch.setattr(run_weekly, "fetch_openalex_journal_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_author_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_broader_reading", lambda: [])
    monkeypatch.setattr(run_weekly, "post_weekly_digest", fake_post)

    assert run_weekly.main() == 0
    assert heuristic_calls == [1]
    assert dry_run_flags == [True]
    assert captured["runs"][0]["claude_cost_usd"] == 0.0


def test_followed_author_paper_skips_relevance_and_gets_its_own_section(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_weekly, "load_state", lambda: {"posted": [], "runs": []})
    monkeypatch.setattr(run_weekly, "save_state", lambda s: captured.update(s))

    # The same paper is surfaced by the RSS topic lane AND by a followed author.
    shared_rss = {"title": "Shared paper", "doi": "10.1/shared", "abstract": "x",
                  "source_lane": "rss", "published": "2026-08-01"}
    by_author = {"title": "Shared paper", "doi": "10.1/shared", "abstract": "x",
                 "source_lane": "openalex_author", "published": "2026-08-01",
                 "matched_authors": ["Jane Q. Smith"]}

    scored = []
    monkeypatch.setattr(run_weekly, "fetch_rss_candidates", lambda: ([shared_rss], []))
    monkeypatch.setattr(run_weekly, "fetch_openalex_journal_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_author_candidates", lambda: [by_author])
    monkeypatch.setattr(run_weekly, "fetch_broader_reading", lambda: [])

    def fake_filter(candidates):
        scored.extend(candidates)
        return [], {"scored": len(candidates), "skipped_no_abstract": 0,
                    "input_tokens": 0, "output_tokens": 0}

    passed = {}

    def fake_post(by_topic, broader, followed_authors=None, dry_run=False):
        passed["followed_authors"] = followed_authors
        return [{"ts": "9", "source_lane": "openalex_author", "topics": ["Followed Authors"],
                 "matched_authors": ["Jane Q. Smith"], "published": "2026-08-01",
                 "posted_date": "2026-08-30", "title_only": False}]

    monkeypatch.setattr(run_weekly, "filter_relevant", fake_filter)
    monkeypatch.setattr(run_weekly, "post_weekly_digest", fake_post)

    assert run_weekly.main() == 0

    # the shared paper never reached the relevance filter
    assert scored == []
    # it was handed to the digest as a followed-author paper
    assert passed["followed_authors"] == [by_author]
    # and recorded under the author lane
    rec = captured["runs"][0]
    assert rec["collected"]["openalex_author"] == 1
    assert rec["posted_by_lane"] == {"openalex_author": 1}
