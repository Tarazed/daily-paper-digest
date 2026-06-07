import os
from typing import Dict

from . import simple_toml


def load_state(path: str) -> Dict[str, Dict[str, str]]:
    if not path or not os.path.exists(path):
        return {}
    raw = simple_toml.load(path)
    papers = raw.get("paper", {})
    state = {}
    for _, values in papers.items():
        if not isinstance(values, dict):
            continue
        paper_id = values.get("id")
        if not paper_id:
            continue
        state[str(paper_id)] = {
            "importance": str(values.get("importance", "normal")),
            "read_status": str(values.get("read_status", "unread")),
            "notes": str(values.get("notes", "")),
        }
    return state
