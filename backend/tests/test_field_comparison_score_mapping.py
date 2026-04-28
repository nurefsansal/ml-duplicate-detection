from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.rule_matching_service import _build_fallback_contact_similarity_comparison


def test_phone_similarity_028_maps_to_score_28_and_weak_match() -> None:
    comparison = _build_fallback_contact_similarity_comparison(
        raw_left_value="054463982",
        raw_right_value="054362862",
        normalized_left_value="054463982",
        normalized_right_value="054362862",
        similarity_score=0.28,
        exact_match=False,
        comparison_method="legacy_tiered_phone_similarity(clean_phone)",
        field_name="Telefon",
    )
    assert comparison["score0To100"] == 28
    assert comparison["comparisonResult"] == "weak_match"


def test_email_similarity_09_maps_to_score_90_and_strong_match() -> None:
    comparison = _build_fallback_contact_similarity_comparison(
        raw_left_value="a@example.com",
        raw_right_value="ab@example.com",
        normalized_left_value="a@example.com",
        normalized_right_value="ab@example.com",
        similarity_score=0.9,
        exact_match=False,
        comparison_method="legacy_hybrid_email_similarity(clean_email+email_normalized_key)",
        field_name="E-posta",
    )
    assert comparison["score0To100"] == 90
    assert comparison["comparisonResult"] == "strong_match"
