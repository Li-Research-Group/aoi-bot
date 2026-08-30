"""Tests for the parts of sources.py that carry logic rather than IO:
the per-lane tagging that lets the stats code attribute a posted paper to
the lane that surfaced it, and the empty-feed detection for dead-feed
alerting."""

from sources import (
    _openalex_to_paper,
    fetch_rss_candidates,
    fetch_openalex_author_candidates,
)


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


def test_fetch_openalex_author_candidates_tags_lane_and_matched_author():
    seen = []

    def fake_get(params, label):
        seen.append(params["filter"])
        return [{
            "title": "Recent work by a followed author",
            "authorships": [{"author": {"display_name": "Jane Q. Smith"}}],
            "primary_location": {"source": {"display_name": "Some Journal"}},
            "doi": "https://doi.org/10.1/xyz",
            "id": "https://openalex.org/W99",
            "publication_date": "2026-08-20",
            "abstract_inverted_index": {"An": [0], "abstract": [1]},
        }]

    authors = {"Jane Q. Smith": "A5023888391", "Unset Person": "FILL_IN"}
    papers = fetch_openalex_author_candidates(authors=authors, get=fake_get)

    assert len(papers) == 1
    assert papers[0]["source_lane"] == "openalex_author"
    assert papers[0]["matched_authors"] == ["Jane Q. Smith"]
    # the FILL_IN placeholder author is skipped, so only one query fired
    assert seen == ["authorships.author.id:A5023888391,from_publication_date:"
                    + __import__("sources")._cutoff_date().isoformat()]


def test_fetch_openalex_author_candidates_accepts_orcid():
    seen = []

    def fake_get(params, label):
        seen.append(params["filter"])
        return []

    fetch_openalex_author_candidates(
        authors={"Corinne Scown": "0000-0003-2078-1126"}, get=fake_get
    )
    cutoff = __import__("sources")._cutoff_date().isoformat()
    # a hyphenated value is an ORCID -> the orcid filter, not author.id
    assert seen == [f"authorships.author.orcid:0000-0003-2078-1126,from_publication_date:{cutoff}"]
