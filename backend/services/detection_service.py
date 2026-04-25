from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import joinedload, sessionmaker

from src.db import create_db_engine
from backend.models.database import DetectionRun, MatchCandidate, NormalizationRun, NormalizedRecord
from backend.schemas.requests import RecordIn
from backend.services.matching_service import (
    DEFAULT_MODEL_VERSION,
    extract_confidence,
    infer_match_type,
    run_matching,
)
from backend.services.normalization_persistence_service import (
    persist_normalization_pipeline,
)
from backend.services.normalization_service import (
    ADDRESS_COLUMN,
    CITY_COLUMN,
    EMAIL_COLUMN,
    NAME_COLUMN,
    PHONE_COLUMN,
    TC_COLUMN,
    build_column_mapping_definitions,
    canonicalize_upload_dataframe,
    metaphone_name_key,
    normalize_email_key,
    to_dataframe,
)

ENGINE = create_db_engine()
SessionLocal = sessionmaker(bind=ENGINE)

DEFAULT_DETECTION_THRESHOLD = 0.30


def _resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalise_mapping_key(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "Ã…Â": "S",
        "Ã…Å¸": "s",
        "Å": "S",
        "ÅŸ": "s",
        "ÃƒÂ": "S",
        "ÃƒÂ¾": "s",
        "Ä": "G",
        "ÄŸ": "g",
        "Ãœ": "U",
        "Ã¼": "u",
        "Ã–": "O",
        "Ã¶": "o",
        "Ã‡": "C",
        "Ã§": "c",
        "Ä°": "I",
        "Ä±": "i",
    }.items():
        text = text.replace(source, target)
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _pick_mapping_value(*mappings: dict[str, Any], aliases: tuple[str, ...]) -> str:
    actual_keys: dict[str, str] = {}
    merged: dict[str, Any] = {}

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        merged.update(mapping)
        for key in mapping.keys():
            actual_keys[_normalise_mapping_key(key)] = key

    for alias in aliases:
        actual_key = actual_keys.get(_normalise_mapping_key(alias))
        if actual_key is None:
            continue
        value = _safe_str(merged.get(actual_key))
        if value:
            return value
    return ""


def _normalized_record_to_matching_row(record: NormalizedRecord) -> dict[str, Any]:
    normalized_payload = (
        record.normalized_payload if isinstance(record.normalized_payload, dict) else {}
    )
    raw_payload = (
        record.raw_record.raw_payload
        if record.raw_record is not None and isinstance(record.raw_record.raw_payload, dict)
        else {}
    )

    clean_name_ordered = _safe_str(
        normalized_payload.get("clean_name") or record.clean_name
    )
    clean_name = _safe_str(
        normalized_payload.get("canonical_name")
        or normalized_payload.get("ordered_name")
        or record.ordered_name
        or clean_name_ordered
    )
    clean_first_name = _safe_str(
        normalized_payload.get("first_name") or record.first_name
    )
    clean_surname = _safe_str(
        normalized_payload.get("last_name") or record.last_name
    )
    clean_email = _safe_str(
        normalized_payload.get("clean_email") or record.clean_email
    )

    return {
        NAME_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(NAME_COLUMN, "adSoyad", "name", "fullName", "full_name"),
        ),
        TC_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(TC_COLUMN, "tcKimlikNo", "tc", "identity", "idNumber"),
        ),
        PHONE_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(PHONE_COLUMN, "telefon", "phone", "mobile"),
        ),
        EMAIL_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(EMAIL_COLUMN, "email", "mail"),
        ),
        CITY_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(CITY_COLUMN, "Sehir", "Şehir", "sehir", "city"),
        ),
        ADDRESS_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(ADDRESS_COLUMN, "adres", "address"),
        ),
        "clean_name": clean_name,
        "clean_name_ordered": clean_name_ordered,
        "clean_first_name": clean_first_name,
        "clean_surname": clean_surname,
        "clean_tc": _safe_str(normalized_payload.get("clean_tc") or record.clean_tc),
        "clean_phone": _safe_str(
            normalized_payload.get("clean_phone") or record.clean_phone
        ),
        "clean_email": clean_email,
        "clean_city": _safe_str(
            normalized_payload.get("clean_city") or record.clean_city
        ),
        "name_phonetic_key": _safe_str(
            normalized_payload.get("name_phonetic_key")
            or normalized_payload.get("name_phonetic")
            or record.name_phonetic
        ),
        "email_normalized_key": _safe_str(
            normalized_payload.get("email_normalized_key")
            or normalize_email_key(clean_email)
        ),
        "name_metaphone_key": _safe_str(
            normalized_payload.get("name_metaphone_key")
            or metaphone_name_key(clean_name)
        ),
        "blocking_key": _safe_str(
            normalized_payload.get("blocking_key") or record.blocking_key
        ),
        "is_valid": bool(
            normalized_payload.get("is_valid")
            if "is_valid" in normalized_payload
            else record.is_valid
        ),
        "normalized_record_id": int(record.id),
        "raw_id": int(record.raw_id),
        "upload_id": int(record.upload_id),
        "normalization_run_id": (
            int(record.normalization_run_id)
            if record.normalization_run_id is not None
            else None
        ),
    }


def _build_matching_dataframe(
    normalized_records: list[NormalizedRecord],
) -> tuple[pd.DataFrame, dict[int, int]]:
    rows = [_normalized_record_to_matching_row(record) for record in normalized_records]
    df_clean = pd.DataFrame(rows)
    index_to_normalized_id = {
        int(index): int(normalized_record_id)
        for index, normalized_record_id in enumerate(
            df_clean.get("normalized_record_id", pd.Series(dtype=int)).tolist()
        )
    }
    return df_clean, index_to_normalized_id


def _resolve_detection_scope(
    *,
    session,
    upload_id: int | None,
    normalization_run_id: int | None,
) -> tuple[int, int | None, list[NormalizedRecord]]:
    resolved_upload_id = upload_id
    resolved_normalization_run_id = normalization_run_id

    if resolved_normalization_run_id is not None:
        normalization_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.id == resolved_normalization_run_id)
            .first()
        )
        if normalization_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Normalization run not found: {resolved_normalization_run_id}",
            )
        resolved_upload_id = int(normalization_run.upload_id)
    elif resolved_upload_id is not None:
        latest_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.upload_id == resolved_upload_id)
            .order_by(NormalizationRun.created_at.desc(), NormalizationRun.id.desc())
            .first()
        )
        if latest_run is not None:
            resolved_normalization_run_id = int(latest_run.id)
    else:
        raise HTTPException(
            status_code=400,
            detail="Either uploadId, normalizationRunId or records must be provided",
        )

    query = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    if resolved_normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
    else:
        query = query.filter(NormalizedRecord.upload_id == resolved_upload_id)

    normalized_records = query.order_by(NormalizedRecord.id.asc()).all()
    if not normalized_records:
        raise HTTPException(
            status_code=404,
            detail="No normalized records found for the requested scope",
        )

    return int(resolved_upload_id), resolved_normalization_run_id, normalized_records


def _persist_match_candidates(
    *,
    session,
    detection_run_id: int,
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> int:
    inserted = 0

    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is None or right_id is None or left_id == right_id:
            continue

        confidence = extract_confidence(payload)
        session.add(
            MatchCandidate(
                detection_run_id=detection_run_id,
                left_id=left_id,
                right_id=right_id,
                score=confidence,
                match_type=infer_match_type(payload),
                decision="pending",
                confidence=confidence,
            )
        )
        inserted += 1

    session.flush()
    return inserted


def run_detection_from_database(
    *,
    upload_id: int | None,
    normalization_run_id: int | None,
    min_rules_to_match: int,
    session_id: str | None,
) -> dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id)
    session = SessionLocal()

    try:
        resolved_upload_id, resolved_normalization_run_id, normalized_records = (
            _resolve_detection_scope(
                session=session,
                upload_id=upload_id,
                normalization_run_id=normalization_run_id,
            )
        )

        detection_run = DetectionRun(
            upload_id=resolved_upload_id,
            normalization_run_id=resolved_normalization_run_id,
            model_version=DEFAULT_MODEL_VERSION,
            threshold=DEFAULT_DETECTION_THRESHOLD,
        )
        session.add(detection_run)
        session.flush()

        df_clean, index_to_normalized_id = _build_matching_dataframe(normalized_records)
        duplicates, resolved_model_version = run_matching(
            df_clean=df_clean,
            min_rules_to_match=min_rules_to_match,
        )
        detection_run.model_version = resolved_model_version

        inserted = _persist_match_candidates(
            session=session,
            detection_run_id=int(detection_run.id),
            duplicates=list(duplicates),
            index_to_normalized_id=index_to_normalized_id,
        )

        session.commit()

        return {
            "sessionId": resolved_session_id,
            "uploadId": resolved_upload_id,
            "normalizationRunId": resolved_normalization_run_id,
            "detectionRunId": int(detection_run.id),
            "candidatePairs": int(
                getattr(duplicates, "candidate_pairs", len(duplicates))
            ),
            "duplicatePairs": int(
                getattr(duplicates, "duplicate_pairs", len(duplicates))
            ),
            "insertedRows": inserted,
            "totalRecords": len(normalized_records),
            "duplicates": list(duplicates),
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}") from exc
    finally:
        session.close()


def detect_core(
    *,
    records: list[RecordIn],
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
    upload_id: int | None = None,
    normalization_run_id: int | None = None,
) -> dict[str, Any]:
    del save_to_db

    if normalization_run_id is not None or upload_id is not None:
        return run_detection_from_database(
            upload_id=upload_id,
            normalization_run_id=normalization_run_id,
            min_rules_to_match=min_rules_to_match,
            session_id=session_id,
        )

    if not records:
        raise HTTPException(
            status_code=400,
            detail="Either uploadId, normalizationRunId or records must be provided",
        )

    resolved_session_id = _resolve_session_id(session_id)
    df_raw = to_dataframe(records)
    mapping_definitions = build_column_mapping_definitions(list(df_raw.columns))
    normalization_result = persist_normalization_pipeline(
        original_df=df_raw.copy(),
        processing_df=df_raw,
        source_type="api",
        source_name="detect_api",
        file_name=f"detect_{resolved_session_id}.json",
        created_by="api_detect",
        mapping_definitions=mapping_definitions,
    )

    return run_detection_from_database(
        upload_id=int(normalization_result["uploadId"]),
        normalization_run_id=int(normalization_result["normalizationRunId"]),
        min_rules_to_match=min_rules_to_match,
        session_id=resolved_session_id,
    )


def detect_file_dataframe(
    *,
    df_original: pd.DataFrame,
    file_name: str,
    source_type: str,
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
    upload_id: int | None = None,
) -> dict[str, Any]:
    del save_to_db

    resolved_session_id = _resolve_session_id(session_id)
    mapping_definitions = build_column_mapping_definitions(
        [str(column) for column in df_original.columns]
    )

    try:
        df_processing = canonicalize_upload_dataframe(df_original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalization_result = persist_normalization_pipeline(
        original_df=df_original,
        processing_df=df_processing,
        source_type=source_type,
        source_name=file_name,
        file_name=file_name,
        created_by="api_detect_file",
        upload_id=upload_id,
        mapping_definitions=mapping_definitions,
    )

    return run_detection_from_database(
        upload_id=int(normalization_result["uploadId"]),
        normalization_run_id=int(normalization_result["normalizationRunId"]),
        min_rules_to_match=min_rules_to_match,
        session_id=resolved_session_id,
    )
