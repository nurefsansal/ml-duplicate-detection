"""
Canonical feature vector for sklearn match-probability training and inference.

Training (`train_match_probability_model`) and prediction (`predict_match_probability`)
must use the same column order and extraction logic so stored models stay aligned with
runtime feature dictionaries from Splink/rules/review.

`ML_FEATURE_SCHEMA_VERSION` is stored in model_status.json on train for auditability.
"""
from __future__ import annotations

from typing import Any

ML_FEATURE_SCHEMA_VERSION = "canonical_v1"

# Order is stable: sklearn / pandas uses these names as feature_names_in_.
CANONICAL_ML_MODEL_FEATURE_COLUMNS: tuple[str, ...] = (
    "name_similarity",
    "email_similarity",
    "phone_exact_match",
    "tc_exact_match",
    "city_exact_match",
    "address_similarity",
)


def flatten_features_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Merge nested `features` payloads (legacy Match rows) into a flat dict."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    nested = raw.get("features")
    if isinstance(nested, dict):
        out.update(nested)
    for k, v in raw.items():
        if k != "features":
            out[k] = v
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def extract_canonical_ml_features(raw: dict[str, Any]) -> dict[str, float]:
    """Map arbitrary raw feature dict → fixed-order floats used by RandomForest train/predict."""
    flat = flatten_features_dict(raw)
    return {
        "name_similarity": _safe_float(flat.get("name_similarity"), 0.0),
        "email_similarity": _safe_float(flat.get("email_similarity"), 0.0),
        "phone_exact_match": float(_safe_int(flat.get("phone_exact_match"), 0)),
        "tc_exact_match": float(_safe_int(flat.get("tc_exact_match"), 0)),
        "city_exact_match": float(_safe_int(flat.get("city_exact_match"), 0)),
        "address_similarity": _safe_float(flat.get("address_similarity"), 0.0),
    }


def canonical_features_to_ordered_row(vec: dict[str, float]) -> list[float]:
    return [float(vec.get(col, 0.0)) for col in CANONICAL_ML_MODEL_FEATURE_COLUMNS]


def model_expects_canonical_features(feature_names: list[str] | tuple[str, ...]) -> bool:
    names = set(feature_names)
    canon = set(CANONICAL_ML_MODEL_FEATURE_COLUMNS)
    return names == canon and len(feature_names) == len(CANONICAL_ML_MODEL_FEATURE_COLUMNS)
