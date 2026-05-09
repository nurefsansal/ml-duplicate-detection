from __future__ import annotations

import json
import math
import pickle
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sqlalchemy.orm import Session, joinedload

from backend.models.database import MatchCandidate, NormalizedRecord, ReviewAction
from backend.services.decision_thresholds import DecisionThresholdsProb
from backend.services.ml_feature_schema import (
    CANONICAL_ML_MODEL_FEATURE_COLUMNS,
    ML_FEATURE_SCHEMA_VERSION,
    extract_canonical_ml_features,
    flatten_features_dict,
    model_expects_canonical_features,
)
from backend.services.scoring_app_settings import (
    compute_weighted_score_breakdown,
    load_scoring_app_settings,
)


MODEL_PATH = Path("backend/models/model.pkl")
MODEL_STATUS_PATH = Path("backend/models/model_status.json")
TRAINING_FEATURE_COLUMNS = list(CANONICAL_ML_MODEL_FEATURE_COLUMNS)


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


def get_latest_review_labels_by_match_id(session: Session) -> dict[int, str]:
    """Latest human decision per match_candidate.id (for training labels and exports)."""
    return _latest_review_decisions(session)


def _latest_review_decisions(session: Session) -> dict[int, str]:
    rows = (
        session.query(ReviewAction)
        .order_by(ReviewAction.match_id.asc(), ReviewAction.decided_at.desc(), ReviewAction.id.desc())
        .all()
    )
    latest: dict[int, str] = {}
    for row in rows:
        if row.match_id in latest:
            continue
        latest[int(row.match_id)] = str(row.decision or "").strip().lower()
    return latest


def train_match_probability_model(session: Session) -> dict[str, Any]:
    # Lazy import: review_service imports ml_service at module load; avoid circular import at import time.
    from backend.services.review_service import derive_canonical_ml_features_for_match_candidate

    review_labels = _latest_review_decisions(session)
    candidates = (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
        .filter(MatchCandidate.decision.in_(["approved", "rejected", "pending"]))
        .all()
    )

    rows: list[dict[str, float]] = []
    labels: list[int] = []
    skipped_missing_records = 0
    for candidate in candidates:
        decision = review_labels.get(int(candidate.id)) or str(candidate.decision or "").strip().lower()
        if decision == "approved":
            label = 1
        elif decision == "rejected":
            label = 0
        else:
            continue

        canon = derive_canonical_ml_features_for_match_candidate(candidate)
        if canon is None:
            skipped_missing_records += 1
            continue
        rows.append(canon)
        labels.append(label)

    if len(rows) < 10:
        raise ValueError("Model eğitimi için en az 10 etiketli kayıt gerekiyor.")
    if len(set(labels)) < 2:
        raise ValueError("Model eğitimi için hem approved hem rejected örnekleri gerekiyor.")

    X = pd.DataFrame(rows, columns=TRAINING_FEATURE_COLUMNS)
    y = pd.Series(labels, dtype="int64")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "total_labeled_samples": int(len(X)),
        "feature_columns": TRAINING_FEATURE_COLUMNS,
        "ml_feature_schema": ML_FEATURE_SCHEMA_VERSION,
        "feature_source": "derived_live",
        "skipped_missing_records": int(skipped_missing_records),
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as model_file:
        pickle.dump(model, model_file)
    with open(MODEL_STATUS_PATH, "w", encoding="utf-8") as status_file:
        json.dump(metrics, status_file, ensure_ascii=False, indent=2)

    return metrics


def get_model_status() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        return {
            "trained": False,
            "model_path": str(MODEL_PATH),
            "message": "Model henüz eğitilmedi.",
        }
    status_payload: dict[str, Any] = {}
    if MODEL_STATUS_PATH.exists():
        with open(MODEL_STATUS_PATH, "r", encoding="utf-8") as status_file:
            data = json.load(status_file)
            if isinstance(data, dict):
                status_payload = data
    return {
        "trained": True,
        "model_path": str(MODEL_PATH),
        **status_payload,
    }


def predict_match_probability(features: dict) -> float:
    flat = flatten_features_dict(features)

    model = _load_model()

    if model is None:
        return _fallback_probability(flat)

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

    # Train=inference: canonical RF models use the same extraction as training rows.
    if model_expects_canonical_features(feature_order):
        canon = extract_canonical_ml_features(flat)
        df_row = pd.DataFrame(
            [[canon[c] for c in feature_order]],
            columns=feature_order,
        )
    else:
        # Legacy pickles trained with expanded integer feature spaces.
        df_row = pd.DataFrame([{col: flat.get(col, 0) for col in feature_order}], columns=feature_order)

    if hasattr(model, "predict_proba"):
        prob = float(model.predict_proba(df_row)[0][1])
        return round(prob, 4)

    if hasattr(model, "predict"):
        pred = float(model.predict(df_row)[0])
        return round(pred, 4)

    return _fallback_probability(flat)


def predict_same_person_probability(features: dict[str, Any]) -> float:
    """
    Public service function for downstream consumers.
    Uses the same preprocessing as inference (canonical extraction inside predict_match_probability).
    """
    return predict_match_probability(features)


def load_ml_scoring_settings(session: Session | None) -> tuple[dict[str, float], DecisionThresholdsProb]:
    """Ayarlar tablosundan ağırlık ve eşikleri okur (session None → varsayılanlar)."""
    return load_scoring_app_settings(session)


def weighted_score_breakdown_from_features(
    features: dict[str, Any],
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    """Ayarlar ağırlıklarıyla 0–100 alan kırılımı (model olasılığından bağımsız)."""
    weights, _ = load_scoring_app_settings(session)
    return compute_weighted_score_breakdown(features, weights)