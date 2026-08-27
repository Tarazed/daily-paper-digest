import json

from daily_paper.digest_state import DigestState, load_digest_state, save_digest_state


def test_digest_state_round_trip_is_atomic(tmp_path):
    path = tmp_path / "digest_state.json"
    state = DigestState(
        last_success={"llm_systems": "2026-08-27T00:00:00Z"},
        sent_ids={"llm_systems": ["arxiv:1"]},
        foundation_review_ids=["arxiv:classic"],
        foundation_review_cursor=1,
    )

    save_digest_state(str(path), state)

    assert load_digest_state(str(path)) == state
    assert not (tmp_path / "digest_state.json.tmp").exists()


def test_load_digest_state_recovers_from_missing_or_invalid_json(tmp_path):
    path = tmp_path / "digest_state.json"
    assert load_digest_state(str(path)) == DigestState()

    path.write_text("not json", encoding="utf-8")
    assert load_digest_state(str(path)) == DigestState()


def test_load_digest_state_normalizes_legacy_shapes(tmp_path):
    path = tmp_path / "digest_state.json"
    path.write_text(
        json.dumps(
            {
                "last_success": {"llm_systems": 123},
                "sent_ids": {"llm_systems": ["a", "a", 2]},
                "cold_start_completed_at": None,
                "foundation_review_ids": ["f1", "f1", 3],
                "foundation_review_cursor": "2",
            }
        ),
        encoding="utf-8",
    )

    state = load_digest_state(str(path))

    assert state.last_success == {"llm_systems": "123"}
    assert state.sent_ids == {"llm_systems": ["a", "2"]}
    assert state.cold_start_completed_at == ""
    assert state.foundation_review_ids == ["f1", "3"]
    assert state.foundation_review_cursor == 2
