import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resolution_service import resolve_match_decision


def test_mid_score_name_only_not_approved() -> None:
    decision = resolve_match_decision(
        0.65,
        {
            "name_similarity": 0.88,
            "tc_exact_match": 0,
            "phone_exact_match": 0,
            "email_similarity": 0.70,
        },
    )
    # TC yokken sadece isim/email benzerliği (exact sinyal olmadan) onay için yeterli değildir.
    assert decision in {"pending", "rejected"}


def test_low_score_rejected() -> None:
    decision = resolve_match_decision(
        0.30,
        {
            "name_similarity": 0.35,
            "tc_exact_match": 0,
            "phone_exact_match": 0,
            "email_exact_match": 0,
            "city_exact_match": 0,
        },
    )
    assert decision == "rejected"


def test_tc_conflict_high_score_not_approved() -> None:
    decision = resolve_match_decision(
        0.99,
        {
            "tc_conflict": 1,
            "name_similarity": 0.98,
            "phone_exact_match": 1,
        },
    )
    assert decision in {"pending", "rejected"}
