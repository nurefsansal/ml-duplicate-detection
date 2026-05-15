from __future__ import annotations

from typing import Any

from backend.services.decision_thresholds import DecisionThresholdsProb


def resolve_match_decision(
    probability: float,
    features: dict,
    *,
    thresholds: DecisionThresholdsProb | None = None,
) -> str:
    """All detection candidates require manual review (no auto approve/reject)."""
    decision, _ = resolve_match_decision_with_trace(probability, features, thresholds=thresholds)
    return decision


def resolve_match_decision_with_trace(
    probability: float,
    features: dict,
    *,
    thresholds: DecisionThresholdsProb | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Detection-time decision: always pending. Risk flags are informational only.
    """
    _ = thresholds
    _ = probability
    safety_overrides: list[dict[str, Any]] = []

    if features.get("tc_conflict", 0) == 1:
        safety_overrides.append(
            {
                "rule": "tc_conflict",
                "effect": "info",
                "detail": "TC Kimlik No çakışması; manuel inceleme önerilir.",
            }
        )
    if features.get("household_risk_flag", 0) == 1:
        safety_overrides.append(
            {
                "rule": "household_risk_flag",
                "effect": "info",
                "detail": "Ortak iletişim / hanehalkı riski; manuel inceleme önerilir.",
            }
        )
    if features.get("muhatap_no_conflict", 0) == 1:
        safety_overrides.append(
            {
                "rule": "muhatap_no_conflict",
                "effect": "info",
                "detail": "Muhatap kodu çakışması; manuel inceleme önerilir.",
            }
        )

    return "pending", safety_overrides
