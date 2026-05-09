import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.scoring_app_settings import compute_weighted_score_breakdown


def test_tc_exact_only_contributes_its_own_weight() -> None:
    breakdown = compute_weighted_score_breakdown(
        {
            "tc_exact_match": 1,
            "tc_present_both": 1,
            "name_present_both": 1,
            "name_similarity": 0.0,
            "first_name_similarity": 0.0,
            "surname_similarity": 0.0,
        },
        {
            "adSoyad": 30.0,
            "tcKimlikNo": 35.0,
            "telefon": 15.0,
            "email": 10.0,
            "muhatapNo": 10.0,
        },
    )

    assert breakdown["components_percent"]["tcKimlikNo"] == 100.0
    assert breakdown["components_percent"]["adSoyad"] == 0.0
    assert breakdown["general_weighted_percent"] == 53.85


def test_surname_exact_does_not_force_full_name_component_to_100() -> None:
    breakdown = compute_weighted_score_breakdown(
        {
            "name_present_both": 1,
            "name_similarity": 0.62,
            "first_name_similarity": 0.28,
            "surname_similarity": 1.0,
            "surname_exact_match": 1,
        },
    )

    assert breakdown["components_percent"]["adSoyad"] == 64.0


def test_missing_field_weight_is_removed_from_denominator() -> None:
    breakdown = compute_weighted_score_breakdown(
        {
            "tc_exact_match": 1,
            "tc_present_both": 1,
            "name_similarity": 0.8,
            "name_present_both": 1,
            "phone_present_both": 0,
            "email_present_both": 0,
            "muhatap_present_both": 0,
        },
        {
            "adSoyad": 30.0,
            "tcKimlikNo": 35.0,
            "telefon": 15.0,
            "email": 10.0,
            "muhatapNo": 10.0,
        },
    )

    assert breakdown["active_component_keys"] == ["adSoyad", "tcKimlikNo"]
    assert breakdown["general_weighted_percent"] == 90.77
