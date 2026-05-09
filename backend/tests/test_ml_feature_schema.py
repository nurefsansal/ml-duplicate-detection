"""Canonical ML feature schema: train/inference alignment."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.ml_feature_schema import (
    CANONICAL_ML_MODEL_FEATURE_COLUMNS,
    extract_canonical_ml_features,
    flatten_features_dict,
    model_expects_canonical_features,
)


def test_flatten_nested_features():
    raw = {"features": {"name_similarity": 0.9}, "score": 1}
    flat = flatten_features_dict(raw)
    assert flat["name_similarity"] == 0.9
    assert flat["score"] == 1


def test_extract_canonical_roundtrip():
    vec = extract_canonical_ml_features(
        {
            "name_similarity": 0.5,
            "email_similarity": 0.2,
            "phone_exact_match": 1,
            "tc_exact_match": 0,
            "city_exact_match": 1,
            "address_similarity": 0.33,
        }
    )
    assert len(vec) == len(CANONICAL_ML_MODEL_FEATURE_COLUMNS)
    assert vec["phone_exact_match"] == 1.0
    assert vec["tc_exact_match"] == 0.0


def test_model_expects_canonical_order_insensitive():
    assert model_expects_canonical_features(list(reversed(CANONICAL_ML_MODEL_FEATURE_COLUMNS)))
