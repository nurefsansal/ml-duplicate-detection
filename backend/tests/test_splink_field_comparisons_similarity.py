from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.requests import RecordIn
from backend.services.rule_matching_service import detect_core
from backend.services.splink_service import _build_phone_field_comparison
from backend.services.feature_service import phone_similarity_score


def make_record(
    ad_soyad: str,
    tc: str = "",
    telefon: str = "",
    email: str = "",
    sehir: str = "",
) -> RecordIn:
    return RecordIn(
        adSoyad=ad_soyad,
        tcKimlikNo=tc,
        telefon=telefon,
        email=email,
        sehir=sehir,
    )


def test_splink_active_email_and_phone_scores_are_non_zero() -> None:
    result: dict[str, Any] = detect_core(
        records=[
            make_record(
                "Doga Yildiz",
                telefon="05430385977",
                email="doga.yildi@hotmail.com",
                sehir="Ankara",
            ),
            make_record(
                "Doga Yildiz",
                telefon="05430385977",
                email="dogayildiz@hotmail.com",
                sehir="Ankara",
            ),
        ],
        min_rules_to_match=1,
        save_to_db=False,
        session_id="pytest-splink-similarity",
    )

    duplicates = result.get("duplicates", [])
    assert duplicates, "Expected at least one duplicate pair"

    pair = duplicates[0]
    assert pair.get("decisionSource") == "splink_plus_rules"
    assert pair["fieldComparisons"]["email"]["score0To100"] > 0
    assert pair["fieldComparisons"]["phone"]["score0To100"] > 0


def test_splink_phone_field_score_uses_similarity_percentage() -> None:
    expected_similarity = phone_similarity_score("054463982", "054362862")
    comparison = _build_phone_field_comparison(
        raw_left_value="054463982",
        raw_right_value="054362862",
        normalized_left_value="054463982",
        normalized_right_value="054362862",
        gamma_value=0,
    )
    assert comparison["score0To100"] == round(expected_similarity * 100)
    if expected_similarity >= 0.85:
        assert comparison["comparisonResult"] == "strong_match"
    elif expected_similarity >= 0.60:
        assert comparison["comparisonResult"] == "partial_match"
    elif expected_similarity >= 0.20:
        assert comparison["comparisonResult"] == "weak_match"
    else:
        assert comparison["comparisonResult"] == "mismatch"
