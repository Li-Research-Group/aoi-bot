"""Smoke test for the monthly report renderer: with state and Slack
stubbed, build_report() must run end to end and surface the pipeline
funnel, the dead-feed warning, the cohort split, and participation."""

import datetime

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
    }
    monkeypatch.setattr(track_reactions, "get_message_reactions",
                        lambda ts: fake_reactions.get(ts, []))
    monkeypatch.setattr(track_reactions, "get_user_name",
                        lambda uid: {"U1": "Zoe Li", "U2": "Sam Ng"}[uid])

    report = track_reactions.build_report()

    assert "*Pipeline*" in report
    assert "70 collected" in report          # 20 + 40 + 10
    assert "feeds empty every run" in report  # Green Chemistry flagged
    assert "title-only (Elsevier): 1 paper," in report
    assert "*Participation*" in report
    assert "ZL: 2 reactions" in report   # "Zoe Li" -> initials only (1👍 + 1👎)
    assert "Zoe" not in report           # no actual names in the report
