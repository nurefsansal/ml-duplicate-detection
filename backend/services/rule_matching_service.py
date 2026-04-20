from __future__ import annotations

from datetime import datetime, UTC
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from src.db import create_db_engine
from src.matching import EntityMatcher, MatchConfig
from src.preprocess import DataCleaner

from backend.schemas.requests import RecordIn
from backend.services.normalization_service import (
    to_dataframe,
    json_rows,
    canonical_name,
    phonetic_name_key,
    metaphone_name_key,
    normalize_email_key,
)
from backend.services.feature_service import build_pair_features
from backend.services.ml_service import predict_match_probability
from backend.services.resolution_service import resolve_match_decision
from backend.services.database_service import (
    UploadService,
    RawDonorService,
    NormalizedDonorService,
    MatchService,
)


def _prepare_clean_dataframe(records: list[RecordIn]):
    df_raw = to_dataframe(records)

    cleaner = DataCleaner()
    df_clean = cleaner.process(df_raw)
    df_clean["clean_name"] = df_clean["clean_name"].apply(canonical_name)
    df_clean["name_phonetic_key"] = df_clean["clean_name"].apply(phonetic_name_key)
    df_clean["name_metaphone_key"] = df_clean["clean_name"].apply(metaphone_name_key)
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


def _split_name_parts(name: str) -> tuple[str, str]:
    value = str(name or "").strip()
    if not value:
        return "", ""
    parts = [p for p in value.split(" ") if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _persist_detection_flow(
    *,
    records: list[RecordIn],
    df_clean,
    enriched_duplicates: list[dict],
    session_id: str,
) -> tuple[int, int]:
    """
    Persists detection workflow to normalized schema:
    uploads -> raw_donors -> normalized_donors -> matches
    """
    engine = create_db_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        upload = UploadService.create_upload(
            db,
            file_name=f"detect_{session_id}.json",
            file_size_bytes=0,
            created_by="api_detect",
        )
        UploadService.update_upload_status(db, upload.id, "processing")

        index_to_norm_id: dict[int, int] = {}

        for row_number, (idx, row) in enumerate(df_clean.iterrows(), start=1):
            first_name, last_name = _split_name_parts(row.get("clean_name", ""))

            raw = RawDonorService.create_raw_donor(
                db,
                upload_id=upload.id,
                row_number=row_number,
                full_name=str(row.get("Ad Soyad", "") or ""),
                email=str(row.get("E-mail", "") or ""),
                phone=str(row.get("Telefon", "") or ""),
                city=str(row.get("Şehir", "") or ""),
            )

            norm = NormalizedDonorService.create_normalized_donor(
                db,
                upload_id=upload.id,
                raw_id=raw.id,
                full_name=str(row.get("clean_name", "") or ""),
                first_name=first_name,
                last_name=last_name,
                email=str(row.get("clean_email", "") or ""),
                phone=str(row.get("clean_phone", "") or ""),
                city=str(row.get("clean_city", "") or ""),
                clean_tc=str(row.get("clean_tc", "") or ""),
                clean_phone=str(row.get("clean_phone", "") or ""),
                clean_email=str(row.get("clean_email", "") or ""),
                clean_city=str(row.get("clean_city", "") or ""),
                email_normalized_key=str(row.get("email_normalized_key", "") or ""),
                name_phonetic_key=str(row.get("name_phonetic_key", "") or ""),
            )

            index_to_norm_id[int(idx)] = int(norm.id)

        matches_data: list[dict] = []
        for payload in enriched_duplicates:
            left_idx = int(payload.get("left_index", -1))
            right_idx = int(payload.get("right_index", -1))

            left_norm_id = index_to_norm_id.get(left_idx)
            right_norm_id = index_to_norm_id.get(right_idx)
            if left_norm_id is None or right_norm_id is None:
                continue

            features = payload.get("features", {}) or {}
            ml_prob = float(payload.get("ml_probability", 0.0) or 0.0)

            matches_data.append(
                {
                    "donor1_id": left_norm_id,
                    "donor2_id": right_norm_id,
                    "similarity": float(features.get("name_similarity", 0.0) or 0.0),
                    "ml_score": ml_prob,
                    "confidence": ml_prob,
                    "features": features,
                    "decision_reason": str(payload.get("decision", "review")),
                }
            )

        if matches_data:
            MatchService.create_matches_batch(db, upload.id, matches_data)

        UploadService.update_total_records(db, upload.id, len(records))
        UploadService.update_upload_status(db, upload.id, "completed")
        db.commit()

        return int(upload.id), len(matches_data)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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
    upload_id: int | None = None

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

    if save_to_db:
        try:
            upload_id, inserted = _persist_detection_flow(
                records=records,
                df_clean=df_clean,
                enriched_duplicates=enriched_duplicates,
                session_id=resolved_session_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"DB save failed: {exc}") from exc

    return {
        "sessionId": resolved_session_id,
        "uploadId": upload_id,
        "candidatePairs": int(len(candidate_pairs)),
        "duplicatePairs": int(len(duplicates_view)),
        "insertedRows": inserted,
        "duplicates": enriched_duplicates,
    }