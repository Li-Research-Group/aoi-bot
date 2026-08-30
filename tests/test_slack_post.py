"""post_weekly_digest posts a header, then every paper / section as its
own top-level channel message -- nothing is threaded."""

import slack_post


def _capture(monkeypatch):
    calls = []

    def fake_post(text):
        calls.append(text)
        return {"ts": f"{len(calls)}.0"}

    monkeypatch.setattr(slack_post, "post_message", fake_post)
    return calls


def test_digest_posts_flat_no_threading(monkeypatch):
    calls = _capture(monkeypatch)

    by_topic = {"Water": [
        {"title": "P1", "journal": "ES&T", "published": "2026-08-01",
         "topics": ["Water"], "doi": "10.1/p1", "source_lane": "rss"},
    ]}
    authors = [
        {"title": "P2", "journal": "Green Chem", "published": "2026-08-02",
         "doi": "10.1/p2", "source_lane": "openalex_author",
         "matched_authors": ["Jane Smith"]},
    ]
    broader = [{"title": "B1", "url": "http://x"}]

    log = slack_post.post_weekly_digest(by_topic, broader, followed_authors=authors)

    # header + 1 paper + author separator + 1 author paper + broader separator + 1 item
    assert len(calls) == 6
    assert calls[0].startswith("*Weekly paper digest")

    # every posted paper still gets its own log entry keyed by its own ts
    assert [e["ts"] for e in log] == ["2.0", "4.0", "6.0"]
