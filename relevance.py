"""
Scores each candidate paper against the group's topic list using the
Claude API, so the Slack digest only carries genuinely relevant papers
instead of everything a broad keyword search turns up.
"""

import json
import os

import anthropic

from config import TOPICS

MODEL = "claude-sonnet-4-6"

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
"""


def score_paper(client: anthropic.Anthropic, paper: dict) -> dict:
    """Returns {"relevant": bool, "topics": [...], "reason": str}."""
    user_content = (
        f"Title: {paper['title']}\n"
        f"Journal: {paper.get('journal', '')}\n"
        f"Abstract: {paper.get('abstract', '(no abstract available)')}"
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        print(f"[warn] could not parse relevance response for '{paper['title'][:60]}': {text[:200]}")
        return {"relevant": False, "topics": [], "reason": "parse error"}
    return result


def filter_relevant(papers: list[dict]) -> list[dict]:
    """Runs score_paper over every candidate and attaches the result.
    Returns only papers judged relevant, each with a "topics" and "reason"
    field added."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kept = []
    for paper in papers:
        # Skip the API call entirely if there's no abstract to judge --
        # title-only relevance calls are unreliable and waste a request.
        if not paper.get("abstract"):
            continue
        result = score_paper(client, paper)
        if result.get("relevant") and result.get("topics"):
            paper["topics"] = result["topics"]
            paper["reason"] = result.get("reason", "")
            kept.append(paper)
    return kept
