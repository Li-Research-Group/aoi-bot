"""Tests for the relevance filter's bookkeeping: it must report how many
papers it scored, how many it skipped for lack of an abstract, and the
Claude token usage -- run_weekly.py feeds those into the run stats record."""

import json

from relevance import filter_relevant, heuristic_filter


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeUsage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _FakeResponse:
    def __init__(self, payload, i=100, o=20):
        self.content = [_FakeBlock(json.dumps(payload))]
        self.usage = _FakeUsage(i, o)


class _FakeMessages:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        return self._outer.responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = _FakeMessages(self)


def test_filter_relevant_reports_usage_and_counts():
    papers = [
        {"title": "On-topic paper", "journal": "Environmental Science & Technology",
         "abstract": "We study emerging contaminant removal from wastewater."},
        {"title": "Off-topic paper", "journal": "Environmental Science & Technology",
         "abstract": "A study of stellar nucleosynthesis."},
    ]
    client = _FakeClient([
        _FakeResponse({"relevant": True, "topics": ["Water/Wastewater Treatment (teaching)"],
                       "reason": "matches"}, i=200, o=30),
        _FakeResponse({"relevant": False, "topics": [], "reason": "no"}, i=150, o=10),
    ])

    kept, acct = filter_relevant(papers, client=client)

    assert [p["title"] for p in kept] == ["On-topic paper"]
    assert acct["scored"] == 2
    assert acct["skipped_no_abstract"] == 0
    assert acct["input_tokens"] == 350
    assert acct["output_tokens"] == 40


def test_filter_relevant_skips_abstractless_untracked_journal_without_a_call():
    papers = [
        {"title": "No abstract, unknown journal", "journal": "Some Random Journal", "abstract": ""},
    ]
    client = _FakeClient([])

    kept, acct = filter_relevant(papers, client=client)

    assert kept == []
    assert client.calls == []            # never spent a Claude call
    assert acct["scored"] == 0
    assert acct["skipped_no_abstract"] == 1


def test_heuristic_filter_matches_topic_keywords_and_spends_no_tokens():
    papers = [
        {"title": "Sargassum hydrothermal liquefaction yields",
         "journal": "Algal Research", "abstract": "Brown seaweed converted via HTL."},
        {"title": "A study of medieval poetry", "journal": "Some Journal",
         "abstract": "Nothing to do with the group's topics."},
    ]
    kept, acct = heuristic_filter(papers)

    assert [p["title"] for p in kept] == ["Sargassum hydrothermal liquefaction yields"]
    kept0 = kept[0]
    assert "Sargassum/Seaweed (HTL, AD, arrested AD)" in kept0["topics"]
    assert kept0["title_only"] is False
    assert "keyword" in kept0["reason"].lower()
    # the whole point: zero Claude usage
    assert acct == {"scored": 2, "skipped_no_abstract": 0,
                    "input_tokens": 0, "output_tokens": 0}


def test_heuristic_filter_skips_abstractless_untracked_journal():
    papers = [{"title": "biobinder supply chain", "journal": "Mystery Journal", "abstract": ""}]
    kept, acct = heuristic_filter(papers)
    assert kept == []
    assert acct["skipped_no_abstract"] == 1
    assert acct["scored"] == 0


def test_heuristic_filter_scores_tracked_journal_on_title_alone():
    papers = [{"title": "Techno-economic analysis methodology for biorefineries",
               "journal": "Journal of Cleaner Production", "abstract": ""}]
    kept, acct = heuristic_filter(papers)
    assert len(kept) == 1
    assert kept[0]["title_only"] is True
