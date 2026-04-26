from __future__ import annotations

import math
import pickle
from pathlib import Path

import pandas as pd


MODEL_PATH = Path("backend/models/model.pkl")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _fallback_probability(features: dict) -> float:
    """
    Eğitilmiş model yoksa domain-aware geçici skor üretir.
    Household risk varsa agresif merge'i engeller.
    """

    score = 0.0

    score += 4.0 * features.get("tc_exact_match", 0)
    score -= 4.5 * features.get("tc_conflict", 0)

    score += 1.5 * features.get("phone_exact_match", 0)
    score += 0.8 * features.get("phone_last7_match", 0)
    score += 1.2 * features.get("email_exact_match", 0)
    score += 0.7 * features.get("city_exact_match", 0)
    score += 1.5 * features.get("muhatap_no_exact_match", 0)
    score -= 1.5 * features.get("muhatap_no_conflict", 0)
    score += 1.0 * features.get("phonetic_exact_match", 0)
    score += 0.7 * features.get("metaphone_exact_match", 0)
    score += 0.6 * features.get("phonetic_close_match", 0)

    score += 2.5 * features.get("name_similarity", 0.0)
    score += 1.0 * features.get("name_jaro_winkler", 0.0)
    score += 0.8 * features.get("name_levenshtein_similarity", 0.0)
    score += 1.2 * features.get("email_similarity", 0.0)
    score += 1.8 * features.get("first_name_similarity", 0.0)
    score += 1.2 * features.get("surname_similarity", 0.0)
    score += 0.5 * features.get("first_name_jaro_winkler", 0.0)
    score += 0.4 * features.get("surname_jaro_winkler", 0.0)

    score += 0.7 * features.get("first_name_exact_match", 0)
    score += 0.6 * features.get("surname_exact_match", 0)

    score += 0.2 * features.get("common_non_empty_fields", 0)

    # Domain risk penalties
    score -= 2.5 * features.get("shared_contact_name_conflict", 0)
    score -= 3.0 * features.get("household_risk_flag", 0)

    score -= 4.0

    return round(_sigmoid(score), 4)


def _load_model():
    if not MODEL_PATH.exists():
        return None

    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_match_probability(features: dict) -> float:
    model = _load_model()

    if model is None:
        return _fallback_probability(features)

    feature_order_v2 = [
        "tc_exact_match",
        "tc_conflict",
        "phone_exact_match",
        "phone_last7_match",
        "email_exact_match",
        "city_exact_match",
        "muhatap_no_exact_match",
        "muhatap_no_conflict",
        "phonetic_exact_match",
        "metaphone_exact_match",
        "phonetic_close_match",
        "name_similarity",
        "name_jaro_winkler",
        "name_levenshtein_similarity",
        "email_similarity",
        "first_name_similarity",
        "surname_similarity",
        "first_name_jaro_winkler",
        "surname_jaro_winkler",
        "first_name_exact_match",
        "surname_exact_match",
        "shared_contact_flag",
        "shared_contact_name_conflict",
        "household_risk_flag",
        "common_non_empty_fields",
    ]

    feature_order_v1 = [
        "tc_exact_match",
        "tc_conflict",
        "phone_exact_match",
        "phone_last7_match",
        "email_exact_match",
        "city_exact_match",
        "phonetic_exact_match",
        "name_similarity",
        "email_similarity",
        "first_name_similarity",
        "surname_similarity",
        "first_name_exact_match",
        "surname_exact_match",
        "shared_contact_flag",
        "shared_contact_name_conflict",
        "household_risk_flag",
        "common_non_empty_fields",
    ]

    # Prefer the exact feature list the model was trained with (avoids mismatch warnings).
    # Falls back to heuristic selection when the attribute is absent (older pickles).
    if hasattr(model, "feature_names_in_"):
        feature_order = list(model.feature_names_in_)
    else:
        n_features = getattr(model, "n_features_in_", None)
        feature_order = feature_order_v2
        if isinstance(n_features, int) and n_features == len(feature_order_v1):
            feature_order = feature_order_v1

    # Build a DataFrame with exactly the columns the model expects.
    # Unknown extras are dropped; missing columns are zero-filled.
    df_row = pd.DataFrame([{col: features.get(col, 0) for col in feature_order}], columns=feature_order)

    if hasattr(model, "predict_proba"):
        prob = float(model.predict_proba(df_row)[0][1])
        return round(prob, 4)

    if hasattr(model, "predict"):
        pred = float(model.predict(df_row)[0])
        return round(pred, 4)

    return _fallback_probability(features)