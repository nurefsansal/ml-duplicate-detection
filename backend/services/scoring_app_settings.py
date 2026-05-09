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

    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _present(name: str, fallback: bool = False) -> bool:
        return bool(_i(name)) if name in features else fallback

    name_available = _present(
        "name_present_both",
        fallback=any(
            [
                _i("first_name_exact_match"),
                _i("surname_exact_match"),
                _f("name_similarity") > 0.0,
                _f("first_name_similarity") > 0.0,
                _f("surname_similarity") > 0.0,
            ]
        ),
    )
    tc_available = _present(
        "tc_present_both",
        fallback=bool(_i("tc_exact_match") or _i("tc_conflict")),
    )
    phone_available = _present(
        "phone_present_both",
        fallback=bool(
            _i("phone_exact_match") or _i("phone_last7_match") or _f("phone_similarity") > 0.0
        ),
    )
    email_available = _present(
        "email_present_both",
        fallback=bool(_i("email_exact_match") or _f("email_similarity") > 0.0),
    )
    muhatap_available = _present(
        "muhatap_present_both",
        fallback=bool(_i("muhatap_no_exact_match") or _i("muhatap_no_conflict")),
    )

    name_part = 0.0
    if name_available:
        name_part = _clamp01(
            max(
                _f("name_similarity"),
                (_f("first_name_similarity") * 0.5) + (_f("surname_similarity") * 0.5),
            )
        )

    tc_part = 0.0
    if tc_available:
        tc_part = 1.0 if _i("tc_exact_match") else 0.0

    phone_part = 0.0
    if phone_available:
        phone_part = _clamp01(max(_f("phone_similarity"), 1.0 if _i("phone_exact_match") else 0.0))

    email_part = 0.0
    if email_available:
        email_part = _clamp01(max(_f("email_similarity"), 1.0 if _i("email_exact_match") else 0.0))

    mu_part = 0.0
    if muhatap_available:
        mu_part = 1.0 if _i("muhatap_no_exact_match") else 0.0

    component_parts = {
        "adSoyad": name_part,
        "tcKimlikNo": tc_part,
        "telefon": phone_part,
        "email": email_part,
        "muhatapNo": mu_part,
    }
    active_components = {
        "adSoyad": name_available,
        "tcKimlikNo": tc_available,
        "telefon": phone_available,
        "email": email_available,
        "muhatapNo": muhatap_available,
    }
    components = {
        key: round(100.0 * _clamp01(value), 2) for key, value in component_parts.items()
    }

    weighted_sum = 0.0
    total_active_weight = 0.0
    active_weights_used: dict[str, float] = {}
    for key, value in component_parts.items():
        weight = max(0.0, float(w.get(key, DEFAULT_WEIGHTS.get(key, 0.0)) or 0.0))
        if not active_components.get(key, False) or weight <= 0.0:
            continue
        weighted_sum += value * weight
        total_active_weight += weight
        active_weights_used[key] = weight

    general = round(100.0 * weighted_sum / total_active_weight, 2) if total_active_weight > 0 else 0.0
    return {
        "components_percent": components,
        "weights_used": {k: float(w.get(k, DEFAULT_WEIGHTS[k])) for k in DEFAULT_WEIGHTS},
        "active_weights_used": active_weights_used,
        "active_component_keys": [key for key, is_active in active_components.items() if is_active],
        "general_weighted_percent": general,
    }
