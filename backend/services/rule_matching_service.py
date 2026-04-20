from __future__ import annotations

from datetime import datetime, UTC
from fastapi import HTTPException

from src.db import create_db_engine, save_duplicates
from src.matching import EntityMatcher, MatchConfig
from src.preprocess import DataCleaner

from backend.schemas.requests import RecordIn
from backend.services.normalization_service import (
    to_dataframe,
    json_rows,
    canonical_name,
    phonetic_name_key,
    normalize_email_key,
)
from backend.services.feature_service import build_pair_features
from backend.services.ml_service import predict_match_probability
from backend.services.resolution_service import resolve_match_decision


def _prepare_clean_dataframe(records: list[RecordIn]):
    df_raw = to_dataframe(records)

    cleaner = DataCleaner()
    df_clean = cleaner.process(df_raw)
    df_clean["clean_name"] = df_clean["clean_name"].apply(canonical_name)
    df_clean["name_phonetic_key"] = df_clean["clean_name"].apply(phonetic_name_key)
    df_clean["email_normalized_key"] = df_clean["clean_email"].apply(normalize_email_key)

    return df_clean


def _build_record_pair_payload(df_clean, row):
    left_idx = row["left_index"]
    right_idx = row["right_index"]

    left_record = df_clean.loc[left_idx].to_dict()
    right_record = df_clean.loc[right_idx].to_dict()

    features = build_pair_features(left_record, right_record)
    ml_probability = predict_match_probability(features)
    decision = resolve_match_decision(ml_probability, features)

    reasons = []

    if features["tc_exact_match"]:
        reasons.append("TC Kimlik No tam eşleşti")
    if features["phone_exact_match"]:
        reasons.append("Telefon normalize edilmiş formatta eşleşti")
    if features["email_exact_match"]:
        reasons.append("E-posta eşleşti")
    if features["phonetic_exact_match"]:
        reasons.append("Fonetik isim anahtarı eşleşti")
    if features["city_exact_match"]:
        reasons.append("Şehir eşleşti")
    if features["name_similarity"] > 0:
        reasons.append(f"Ad soyad benzerliği: {features['name_similarity']:.2f}")

    return {
        "left_index": int(left_idx),
        "right_index": int(right_idx),
        "record1": left_record,
        "record2": right_record,
        "features": features,
        "ml_probability": ml_probability,
        "decision": decision,
        "reasons": reasons,
    }


def detect_core(
    records: list[RecordIn],
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
):
    df_clean = _prepare_clean_dataframe(records)

    matcher = EntityMatcher(config=MatchConfig(min_rules_to_match=min_rules_to_match))
    candidate_pairs, _, duplicates_features = matcher.find_duplicates(df_clean)
    duplicates_view = matcher.duplicates_as_dataframe(df_clean, duplicates_features)

    resolved_session_id = session_id or str(int(datetime.now(tz=UTC).timestamp() * 1000))
    inserted = 0

    enriched_duplicates = []

    if not duplicates_view.empty:
        working_df = duplicates_view.copy()

        # eski matcher output isimleri korunamadıysa esnek yaklaşım
        if "left_index" not in working_df.columns or "right_index" not in working_df.columns:
            possible_left_cols = ["left_index", "left_id", "record_1_index", "idx_1"]
            possible_right_cols = ["right_index", "right_id", "record_2_index", "idx_2"]

            left_col = next((c for c in possible_left_cols if c in working_df.columns), None)
            right_col = next((c for c in possible_right_cols if c in working_df.columns), None)

            if left_col is None or right_col is None:
                # fallback: eski davranışı koru
                enriched_duplicates = json_rows(working_df)
            else:
                working_df = working_df.rename(columns={left_col: "left_index", right_col: "right_index"})

        if not enriched_duplicates:
            for _, row in working_df.iterrows():
                enriched_duplicates.append(_build_record_pair_payload(df_clean, row))

    if save_to_db and not duplicates_view.empty:
        try:
            engine = create_db_engine()
            inserted = save_duplicates(engine, duplicates_view, resolved_session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"DB save failed: {exc}") from exc

    return {
        "sessionId": resolved_session_id,
        "candidatePairs": int(len(candidate_pairs)),
        "duplicatePairs": int(len(duplicates_view)),
        "insertedRows": inserted,
        "duplicates": enriched_duplicates,
    }