import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resolution_service import resolve_match_decision


def test_different_tc_same_name_same_phone_is_not_approved() -> None:
    decision = resolve_match_decision(
        0.98,
        {
            "tc_conflict": 1,
            "name_similarity": 0.96,
            "phone_exact_match": 1,
            "email_exact_match": 0,
            "muhatap_no_exact_match": 0,
        },
    )
    assert decision != "approved"


def test_same_tc_similar_name_is_approved() -> None:
    decision = resolve_match_decision(
        0.55,
        {
            "tc_exact_match": 1,
            "name_similarity": 0.88,
            "household_risk_flag": 0,
            "muhatap_no_conflict": 0,
            "same_surname_name_conflict": 0,
        },
    )
    assert decision == "approved"


def test_no_tc_only_high_name_not_approved() -> None:
    decision = resolve_match_decision(
        0.92,
        {
            "tc_exact_match": 0,
            "tc_conflict": 0,
            "name_similarity": 0.90,
            "phone_exact_match": 0,
            "email_exact_match": 0,
            "muhatap_no_exact_match": 0,
        },
    )
    assert decision != "approved"


def test_no_tc_high_name_with_phone_exact_can_be_approved_or_pending() -> None:
    decision = resolve_match_decision(
        0.78,
        {
            "tc_exact_match": 0,
            "tc_conflict": 0,
            "name_similarity": 0.90,
            "phone_exact_match": 1,
            "email_exact_match": 0,
            "muhatap_no_exact_match": 0,
        },
    )
    assert decision in {"approved", "pending"}


def test_household_risk_blocks_approved() -> None:
    decision = resolve_match_decision(
        0.95,
        {
            "tc_exact_match": 0,
            "tc_conflict": 0,
            "household_risk_flag": 1,
            "name_similarity": 0.95,
            "phone_exact_match": 1,
            "email_exact_match": 0,
            "muhatap_no_exact_match": 0,
        },
    )
    assert decision != "approved"
