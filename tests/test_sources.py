"""Tests for the parts of sources.py that carry logic rather than IO:
the per-lane tagging that lets the stats code attribute a posted paper to
the lane that surfaced it, and the empty-feed detection for dead-feed
alerting."""

from sources import _openalex_to_paper, fetch_rss_candidates


def test_openalex_to_paper_tags_the_lane_it_came_from():
    work = {
        "title": "A paper",
        "authorships": [{"author": {"display_name": "Jane Smith"}}],
        "primary_location": {"source": {"display_name": "Some Journal"}},
        "doi": "https://doi.org/10.1/abc",
        "id": "https://openalex.org/W1",
        "publication_date": "2026-08-01",
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
    }
    assert _openalex_to_paper(work, lane="openalex_journal")["source_lane"] == "openalex_journal"
    assert _openalex_to_paper(work, lane="openalex_keyword")["source_lane"] == "openalex_keyword"


def test_openalex_to_paper_defaults_lane_for_back_compat():
    assert _openalex_to_paper({"title": "x"})["source_lane"] == "openalex"


def test_fetch_rss_reports_feeds_that_yield_nothing():
    calls = []

    def fake_parse(url):
        calls.append(url)
        if "gc" in url:               # Green Chemistry -> nothing
            return []
        if "broken" in url:           # a feed that errors
            raise RuntimeError("boom")
        return [{
            "title": "T", "url": "u", "abstract": "a",
            "published": None, "authors": [], "doi": "10.1/x",
        }]

    journals = {
        "Green Chemistry": "http://feeds.rsc.org/rss/gc",
        "Broken Journal": "http://example.com/broken",
        "Good Journal": "http://example.com/ok",
    }
    papers, empty_feeds = fetch_rss_candidates(journals=journals, parse=fake_parse)

    assert sorted(empty_feeds) == ["Broken Journal", "Green Chemistry"]
    assert [p["journal"] for p in papers] == ["Good Journal"]
