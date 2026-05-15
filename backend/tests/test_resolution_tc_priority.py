"""Detection decisions are always pending (no auto approve/reject)."""
from backend.services.resolution_service import resolve_match_decision


def test_always_pending_despite_high_score() -> None:
    decision = resolve_match_decision(
        0.99,
        {
            "tc_exact_match": 1,
            "phone_exact_match": 1,
            "name_similarity": 0.95,
        },
    )
    assert decision == "pending"


def test_always_pending_despite_tc_conflict() -> None:
    decision = resolve_match_decision(
        0.99,
        {"tc_conflict": 1, "phone_exact_match": 1},
    )
    assert decision == "pending"
