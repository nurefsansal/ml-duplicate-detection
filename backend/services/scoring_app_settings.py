"""
Loads scoring-related rows from app_settings (weights, thresholds).

Threshold keys match Ayarlar / migration 003 (0–100 integers):
  otoOnayla, bayrakla, yoksay
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.database import AppSettings
from backend.services.decision_thresholds import DecisionThresholdsProb

DEFAULT_WEIGHTS: dict[str, float] = {
    "adSoyad": 30.0,
    "tcKimlikNo": 35.0,
    "telefon": 15.0,
    "email": 10.0,
    "muhatapNo": 10.0,
}


def _merge_weights(raw: dict[str, Any] | None) -> dict[str, float]:
    out = {k: float(v) for k, v in DEFAULT_WEIGHTS.items()}
    if not isinstance(raw, dict):
        return out
    for key in DEFAULT_WEIGHTS:
        if key in raw and raw[key] is not None:
            try:
                out[key] = float(raw[key])
            except (TypeError, ValueError):
                continue
    return out


def load_scoring_app_settings(session: Session | None) -> tuple[dict[str, float], DecisionThresholdsProb]:
    """
    Safe loader: missing rows or DB errors fall back to defaults.
    """
    weights = dict(DEFAULT_WEIGHTS)
    raw_thresholds: dict[str, Any] | None = None

    if session is not None:
        try:
            rows = session.query(AppSettings).filter(AppSettings.key.in_(["weights", "thresholds"])).all()
            by_key = {r.key: r.value for r in rows}
            if isinstance(by_key.get("weights"), dict):
                weights = _merge_weights(by_key["weights"])
            if "thresholds" in by_key:
                raw_thresholds = by_key["thresholds"] if isinstance(by_key["thresholds"], dict) else None
        except Exception:
            weights = _merge_weights(None)
            raw_thresholds = None

    return weights, DecisionThresholdsProb.from_raw(raw_thresholds)


def compute_weighted_score_breakdown(
    features: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    UI-oriented 0–100 breakdown using Ayarlar weights (not the RF model).
    Maps feature signals to weight buckets.
    """
    w = weights or dict(DEFAULT_WEIGHTS)
    total_w = sum(max(0.0, w.get(k, 0.0)) for k in DEFAULT_WEIGHTS) or 1.0

    def _f(name: str, default: float = 0.0) -> float:
        try:
            return float(features.get(name, default) or 0.0)
        except (TypeError, ValueError):
            return default

    def _i(name: str) -> int:
        try:
            return int(features.get(name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    name_part = max(
        _f("name_similarity"),
        _f("first_name_similarity") * 0.5 + _f("surname_similarity") * 0.5,
    )
    name_part = max(name_part, 1.0 if _i("first_name_exact_match") or _i("surname_exact_match") else 0.0)

    tc_part = 1.0 if _i("tc_exact_match") else (0.0 if _i("tc_conflict") else 0.35 * _f("name_similarity"))

    phone_part = 1.0 if _i("phone_exact_match") else (1.0 if _i("phone_last7_match") else 0.0)

    email_part = max(_f("email_similarity"), 1.0 if _i("email_exact_match") else 0.0)

    mu_part = 1.0 if _i("muhatap_no_exact_match") else (0.0 if _i("muhatap_no_conflict") else 0.5)

    components = {
        "adSoyad": round(100.0 * name_part, 2),
        "tcKimlikNo": round(100.0 * max(0.0, min(1.0, tc_part)), 2),
        "telefon": round(100.0 * max(0.0, min(1.0, phone_part)), 2),
        "email": round(100.0 * max(0.0, min(1.0, email_part)), 2),
        "muhatapNo": round(100.0 * max(0.0, min(1.0, mu_part)), 2),
    }

    weighted_sum = 0.0
    for key, pct in components.items():
        weight = max(0.0, float(w.get(key, DEFAULT_WEIGHTS.get(key, 0.0)) or 0.0))
        weighted_sum += (pct / 100.0) * weight

    general = round(100.0 * weighted_sum / total_w, 2)
    return {
        "components_percent": components,
        "weights_used": {k: float(w.get(k, DEFAULT_WEIGHTS[k])) for k in DEFAULT_WEIGHTS},
        "general_weighted_percent": general,
    }
