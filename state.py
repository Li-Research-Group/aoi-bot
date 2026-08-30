"""Simple JSON-file state store, committed back into the repo by the
GitHub Actions workflow after each run. Holds two logs:

  - "posted": every paper ever posted (message ts, journal, topics,
    lane, publication date) so track_reactions.py can look up reaction
    counts later, and so re-runs don't re-post the same paper twice.
  - "runs": one stats record per weekly run (see stats.build_run_record)
    -- the pipeline funnel, per-lane counts, Claude cost, dead feeds.
"""

import json
import os

from config import STATE_FILE


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": [], "runs": []}
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
    state.setdefault("posted", [])
    state.setdefault("runs", [])  # backfill: older state files predate this
    return state


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def already_posted_keys(state: dict) -> set:
    return {(entry.get("doi") or entry["title"].strip().lower()) for entry in state["posted"]}


def append_posted(state: dict, new_entries: list[dict]) -> None:
    state["posted"].extend(new_entries)


def append_run(state: dict, run_record: dict) -> None:
    state.setdefault("runs", []).append(run_record)
