"""Integration test for run_weekly.main(): with the network lanes and the
Slack post stubbed out, one full pass must leave a stats record in
state["runs"] carrying the funnel numbers, the dead feed, and the Claude
token usage."""

import run_weekly


def _stub_pipeline(monkeypatch, *, rss, empty_feeds, relevant, acct, log):
    monkeypatch.setattr(run_weekly, "fetch_rss_candidates", lambda: (rss, empty_feeds))
    monkeypatch.setattr(run_weekly, "fetch_openalex_journal_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_openalex_candidates", lambda: [])
    monkeypatch.setattr(run_weekly, "fetch_broader_reading", lambda: [])
    monkeypatch.setattr(run_weekly, "filter_relevant", lambda candidates: (relevant, acct))
    monkeypatch.setattr(run_weekly, "post_weekly_digest", lambda by_topic, broader: log)


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
    assert rec["collected"] == {"rss": 1, "openalex_journal": 0, "openalex_keyword": 0}
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
