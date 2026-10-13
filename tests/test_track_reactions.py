"""Smoke test for the monthly report renderer: with state and Slack
stubbed, build_report() must run end to end and surface the pipeline
funnel, the dead-feed warning, the cohort split, and participation."""

import datetime

import pytest

import track_reactions


def test_build_report_renders_all_sections(monkeypatch):
    recent = datetime.date.today().isoformat()

    state = {
        "posted": [
            {"ts": "1", "journal": "Environmental Science & Technology",
             "topics": ["Water/Wastewater Treatment (teaching)"], "title_only": False,
             "published": "2026-08-01", "posted_date": recent, "title": "A good paper"},
            {"ts": "2", "journal": "Water Research",
             "topics": ["Water/Wastewater Treatment (teaching)"], "title_only": True,
             "published": "2026-08-10", "posted_date": recent, "title": "A title-only paper"},
            {"ts": "3", "journal": "Some Journal", "topics": ["Followed Authors"],
             "title_only": False, "source_lane": "openalex_author",
             "matched_authors": ["Jane Q. Smith"],
             "published": "2026-08-15", "posted_date": recent, "title": "Followed author paper"},
        ],
        "runs": [
            {"date": recent, "collected": {"rss": 20, "openalex_journal": 40, "openalex_keyword": 10},
             "duplicates_removed": 12, "already_posted_removed": 5, "scored": 53,
             "skipped_no_abstract": 8, "relevant": 9, "posted": 6,
             "posted_by_lane": {"rss": 4, "openalex_journal": 2},
             "claude_cost_usd": 0.42, "empty_feeds": ["Green Chemistry"]},
        ],
    }
    monkeypatch.setattr(track_reactions, "load_state", lambda: state)

    fake_reactions = {
        "1": [{"name": "thumbsup", "count": 2, "users": ["U1", "U2"]}],
        "2": [{"name": "thumbsdown", "count": 1, "users": ["U1"]}],
        "3": [{"name": "thumbsup", "count": 1, "users": ["U2"]}],
    }
    monkeypatch.setattr(track_reactions, "get_message_reactions",
                        lambda ts: fake_reactions.get(ts, []))
    monkeypatch.setattr(track_reactions, "get_user_name",
                        lambda uid: {"U1": "Maria Santos", "U2": "Sam Ng"}[uid])

    report = track_reactions.build_report()

    assert "*Pipeline*" in report
    assert "70 collected" in report          # 20 + 40 + 10
    assert "feeds empty every run" in report  # Green Chemistry flagged
    assert "title-only (Elsevier): 1 paper," in report
    assert "*Participation*" in report
    assert "MS: 2 reactions" in report   # "Maria Santos" -> initials only (1👍 + 1👎)
    assert "Maria" not in report           # reactor names never shown in full
    # followed authors: named in full (the section is about tuning follows)
    assert "*Followed authors*" in report
    assert "Jane Q. Smith: 1 paper, 100% upvoted" in report


def test_get_message_reactions_normalizes_slack_names(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    payload = {"ok": True, "message": {"reactions": [
        {"name": "+1", "count": 2, "users": ["U1", "U2"]},
        {"name": "+1::skin-tone-3", "count": 1, "users": ["U3"]},
        {"name": "-1", "count": 1, "users": ["U1"]},
        {"name": "eyes", "count": 1, "users": ["U2"]},
    ]}}

    class R:
        def json(self):
            return payload

    monkeypatch.setattr(track_reactions.requests, "get", lambda *a, **k: R())
    reactions = track_reactions.get_message_reactions("1")
    assert track_reactions._counts(reactions) == (3, 1)
    assert {r["name"]: r["users"] for r in reactions}["thumbsup"] == ["U1", "U2", "U3"]


def test_get_message_reactions_raises_on_real_errors(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    class R:
        def json(self):
            return {"ok": False, "error": "missing_scope"}

    monkeypatch.setattr(track_reactions.requests, "get", lambda *a, **k: R())
    with pytest.raises(RuntimeError):
        track_reactions.get_message_reactions("1")


def test_count_reactions_window_and_totals(monkeypatch):
    import count_reactions
    today = datetime.date.today()
    old = (today - datetime.timedelta(days=90)).isoformat()
    new = today.isoformat()
    state = {"posted": [
        {"ts": "1", "title": "Old", "journal": "J", "posted_date": old},
        {"ts": "2", "title": "New", "journal": "J", "posted_date": new},
    ]}
    monkeypatch.setattr(count_reactions, "load_state", lambda: state)
    monkeypatch.setattr(count_reactions.time, "sleep", lambda s: None)
    monkeypatch.setattr(count_reactions.tr, "get_message_reactions", lambda ts: [
        {"name": "thumbsup", "count": 1, "users": ["U1"]}])
    monkeypatch.setattr(count_reactions.tr, "get_user_name", lambda u: "Maria Santos")
    assert "2 papers" in count_reactions.build_count(None)
    out = count_reactions.build_count(30)
    assert "last 30 days): 1 papers" in out and "Total 👍 1" in out
    assert count_reactions._parse_days("all") is None and count_reactions._parse_days("45") == 45
