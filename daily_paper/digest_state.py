import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class DigestState:
    last_success: Dict[str, str] = field(default_factory=dict)
    sent_ids: Dict[str, List[str]] = field(default_factory=dict)
    cold_start_completed_at: str = ""
    foundation_review_ids: List[str] = field(default_factory=list)
    foundation_review_cursor: int = 0


def load_digest_state(path: str) -> DigestState:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError, TypeError):
        return DigestState()
    if not isinstance(values, dict):
        return DigestState()

    last_success = _string_mapping(values.get("last_success"))
    sent_ids = {
        str(track): _unique_strings(ids)
        for track, ids in (values.get("sent_ids") or {}).items()
        if isinstance(ids, list)
    } if isinstance(values.get("sent_ids") or {}, dict) else {}
    try:
        cursor = max(0, int(values.get("foundation_review_cursor", 0) or 0))
    except (TypeError, ValueError):
        cursor = 0
    return DigestState(
        last_success=last_success,
        sent_ids=sent_ids,
        cold_start_completed_at=str(values.get("cold_start_completed_at") or ""),
        foundation_review_ids=_unique_strings(values.get("foundation_review_ids")),
        foundation_review_cursor=cursor,
    )


def save_digest_state(path: str, state: DigestState) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(asdict(state), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _string_mapping(values) -> Dict[str, str]:
    if not isinstance(values, dict):
        return {}
    return {str(key): str(value) for key, value in values.items() if value is not None}


def _unique_strings(values) -> List[str]:
    result = []
    for value in values or []:
        text = str(value)
        if text not in result:
            result.append(text)
    return result
