import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.decision_thresholds import DecisionThresholdsProb
from backend.services.resolution_service import resolve_match_decision


def test_thresholds_do_not_auto_approve_anymore() -> None:
    loose = DecisionThresholdsProb(auto_approve=0.60, manual_review=0.50, reject=0.40)
    decision = resolve_match_decision(
        0.85,
        {
            "tc_exact_match": 0,
            "phone_exact_match": 1,
            "email_exact_match": 0,
            "name_similarity": 0.92,
            "first_name_exact_match": 1,
        },
        thresholds=loose,
    )
    assert decision == "pending"


def test_strict_thresholds_also_pending() -> None:
    strict = DecisionThresholdsProb(auto_approve=0.995, manual_review=0.75, reject=0.50)
    decision = resolve_match_decision(
        0.97,
        {
            "tc_exact_match": 0,
            "phone_exact_match": 1,
            "email_exact_match": 0,
            "name_similarity": 0.92,
            "first_name_exact_match": 1,
        },
        thresholds=strict,
    )
    assert decision == "pending"
