"""
Scores each candidate paper against the group's topic list using the
Claude API, so the Slack digest only carries genuinely relevant papers
instead of everything a broad keyword search turns up.
"""

import json
import os

from config import JOURNALS, JOURNAL_ISSNS, TOPICS

MODEL = "claude-sonnet-4-6"

# Papers from a tracked journal with no abstract (Elsevier releases none) are
# still scored -- on the title alone. Papers from anywhere else with no
# abstract are dropped: title-only scoring of the whole OpenAlex firehose is
# too noisy.
_TRACKED_JOURNALS = set(JOURNALS) | set(JOURNAL_ISSNS)

_TOPIC_DESCRIPTIONS = "\n".join(
    f"- {name}: {', '.join(cfg['keywords'])}" for name, cfg in TOPICS.items()
)

_SYSTEM_PROMPT = f"""You screen research paper abstracts for a research group's weekly \
literature digest. The group's topics are:

{_TOPIC_DESCRIPTIONS}

For the given paper, decide which of these topics (if any) it is genuinely \
relevant to -- not just superficially keyword-adjacent. A paper can match \
zero, one, or more than one topic. Respond with ONLY a JSON object, no \
other text, in this exact shape:

{{"relevant": true/false, "topics": ["<topic name>", ...], "reason": "<one short sentence>"}}

If "relevant" is false, "topics" should be an empty list.

Some papers have no abstract (the publisher does not release one). For those, \
judge from the title and journal alone and be conservative -- only mark it \
relevant if the title clearly and specifically points to one of the topics.
"""


def score_paper(client, paper: dict) -> tuple[dict, tuple[int, int]]:
    """Returns ({"relevant": bool, "topics": [...], "reason": str},
    (input_tokens, output_tokens)) -- the token counts feed the run stats."""
    abstract = (paper.get("abstract") or "").strip()
    body = (
        f"Abstract: {abstract}"
        if abstract
        else "Abstract: (none available -- judge from the title and journal, conservatively)"
    )
    user_content = f"Title: {paper['title']}\nJournal: {paper.get('journal', '')}\n{body}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    usage = getattr(response, "usage", None)
    tokens = (getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        print(f"[warn] could not parse relevance response for '{paper['title'][:60]}': {text[:200]}")
        return {"relevant": False, "topics": [], "reason": "parse error"}, tokens
    return result, tokens


def filter_relevant(papers: list[dict], client=None) -> tuple[list[dict], dict]:
    """Runs score_paper over every candidate and attaches the result.

    Returns (kept, accounting) where kept is the papers judged relevant
    (each with "topics"/"reason"/"title_only" added) and accounting is
    {"scored", "skipped_no_abstract", "input_tokens", "output_tokens"}
    for the run stats record. `client` is injected in tests; production
    callers omit it and a real Anthropic client is built here."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kept = []
    scored = skipped_no_abstract = in_tokens = out_tokens = 0
    for paper in papers:
        has_abstract = bool((paper.get("abstract") or "").strip())
        # No abstract + not a tracked journal -> skip (see _TRACKED_JOURNALS).
        if not has_abstract and paper.get("journal", "") not in _TRACKED_JOURNALS:
            skipped_no_abstract += 1
            continue
        result, (ti, to) = score_paper(client, paper)
        scored += 1
        in_tokens += ti
        out_tokens += to
        if result.get("relevant") and result.get("topics"):
            paper["topics"] = result["topics"]
            paper["reason"] = result.get("reason", "")
            paper["title_only"] = not has_abstract
            kept.append(paper)
    acct = {
        "scored": scored,
        "skipped_no_abstract": skipped_no_abstract,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
    }
    return kept, acct
