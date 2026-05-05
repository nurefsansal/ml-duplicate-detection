from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from backend.services.rule_matching_service import _legacy_detection
from backend.services.decision_thresholds import DecisionThresholdsProb
from backend.services.splink_service import DetectionResults, run_splink_detection

logger = logging.getLogger(__name__)

DEFAULT_MODEL_VERSION = "splink_plus_rules_v1"
FALLBACK_MODEL_VERSION = "fallback_legacy_v1"


def run_matching(
    *,
    df_clean: pd.DataFrame,
    min_rules_to_match: int,
    scoring_weights: dict[str, float] | None = None,
    decision_thresholds: DecisionThresholdsProb | None = None,
) -> tuple[DetectionResults, str]:
    try:
        return (
            run_splink_detection(
                df_clean,
                scoring_weights=scoring_weights,
                decision_thresholds=decision_thresholds,
            ),
            DEFAULT_MODEL_VERSION,
        )
    except Exception as exc:
        logger.warning("Splink failed, falling back to legacy: %s", exc)
        return (
            _legacy_detection(
                df_clean,
                min_rules_to_match,
                scoring_weights=scoring_weights,
                decision_thresholds=decision_thresholds,
            ),
            FALLBACK_MODEL_VERSION,
        )


def extract_confidence(payload: dict[str, Any]) -> float:
    for key in ("splinkMatchProbability", "ml_probability"):
        value = payload.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def infer_match_type(payload: dict[str, Any]) -> str:
    decision_source = str(payload.get("decisionSource", "") or "").lower()
    features = payload.get("features", {}) or {}

    if decision_source.startswith("splink"):
        return "splink"
    if any(
        bool(features.get(key))
        for key in ("tc_exact_match", "phone_exact_match", "email_exact_match")
    ):
        return "exact"
    if any(
        bool(features.get(key))
        for key in ("phonetic_exact_match", "metaphone_exact_match")
    ):
        return "phonetic"
    if float(features.get("name_similarity", 0.0) or 0.0) > 0:
        return "fuzzy"
    return "ml"
