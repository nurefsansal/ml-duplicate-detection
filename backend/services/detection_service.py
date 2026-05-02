from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import joinedload, sessionmaker

logger = logging.getLogger(__name__)

from src.db import create_db_engine
from backend.models.database import DetectionRun, MatchCandidate, NormalizationRun, NormalizedRecord
from backend.services.job_service import update_job_progress
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
    MUHATAP_NO_COLUMN,
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
DETECTION_SYNC_MAX_RECORDS = int(os.getenv("DETECTION_SYNC_MAX_RECORDS", "50000"))


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
        MUHATAP_NO_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(MUHATAP_NO_COLUMN, "muhatap_no", "muhatap kodu", "customer_id", "donor_id"),
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
        "clean_muhatap_no": _safe_str(
            normalized_payload.get("clean_muhatap_no")
            or (record.clean_muhatap_no if hasattr(record, "clean_muhatap_no") else "")
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
                detail=f"Normalizasyon çalışması bulunamadı: ID={resolved_normalization_run_id}",
            )
        resolved_upload_id = int(normalization_run.upload_id)
        logger.info(
            "[detect] normalizationRunId=%s → upload_id=%s",
            resolved_normalization_run_id,
            resolved_upload_id,
        )
    elif resolved_upload_id is not None:
        latest_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.upload_id == resolved_upload_id)
            .order_by(NormalizationRun.created_at.desc(), NormalizationRun.id.desc())
            .first()
        )
        if latest_run is not None:
            resolved_normalization_run_id = int(latest_run.id)
            logger.info(
                "[detect] uploadId=%s → latest normalizationRunId=%s",
                resolved_upload_id,
                resolved_normalization_run_id,
            )
        else:
            logger.info(
                "[detect] uploadId=%s → no normalization run found, filtering by upload_id directly",
                resolved_upload_id,
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="uploadId, normalizationRunId veya records alanlarından en az biri sağlanmalıdır.",
        )

    # Explicitly scoped query — never scans full normalized_records table
    query = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    if resolved_normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
        logger.info(
            "[detect] Scope: normalized_records WHERE normalization_run_id=%s",
            resolved_normalization_run_id,
        )
    else:
        query = query.filter(NormalizedRecord.upload_id == resolved_upload_id)
        logger.info(
            "[detect] Scope: normalized_records WHERE upload_id=%s",
            resolved_upload_id,
        )

    normalized_records = query.order_by(NormalizedRecord.id.asc()).all()
    logger.info("[detect] Kapsam içi normalize kayıt sayısı: %d", len(normalized_records))

    if not normalized_records:
        raise HTTPException(
            status_code=404,
            detail=(
                "Bu yükleme için normalize edilmiş kayıt bulunamadı. "
                "Önce Veri Normalizasyon adımını tamamlayın."
            ),
        )

    return int(resolved_upload_id), resolved_normalization_run_id, normalized_records


def _resolve_detection_scope_for_sync(
    *,
    session,
    upload_id: int | None,
    normalization_run_id: int | None,
    max_records: int,
) -> tuple[int, int | None, int, list[NormalizedRecord]]:
    t_scope = time.monotonic()
    if upload_id is None and normalization_run_id is None:
        raise HTTPException(
            status_code=400,
            detail="Mükerrer tespit için uploadId veya normalizationRunId zorunludur.",
        )

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
                detail=f"Normalizasyon çalışması bulunamadı: ID={resolved_normalization_run_id}",
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

    count_query = session.query(NormalizedRecord.id)
    if resolved_normalization_run_id is not None:
        count_query = count_query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
    else:
        count_query = count_query.filter(NormalizedRecord.upload_id == resolved_upload_id)

    record_count = count_query.count()
    logger.info(
        "[detect] Scope count: uploadId=%s normalizationRunId=%s record_count=%d elapsed=%.2fs",
        resolved_upload_id,
        resolved_normalization_run_id,
        record_count,
        time.monotonic() - t_scope,
    )

    if record_count > max_records:
        logger.warning(
            "[detect] Sync limit exceeded: uploadId=%s normalizationRunId=%s record_count=%d limit=%d",
            resolved_upload_id,
            resolved_normalization_run_id,
            record_count,
            max_records,
        )
        raise HTTPException(
            status_code=413,
            detail="Bu veri seti senkron mükerrer tespit için çok büyük. Background job gereklidir.",
        )

    if record_count == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "Bu yükleme için normalize edilmiş kayıt bulunamadı. "
                "Önce Veri Normalizasyon adımını tamamlayın."
            ),
        )

    query = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    if resolved_normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
    else:
        query = query.filter(NormalizedRecord.upload_id == resolved_upload_id)

    normalized_records = query.order_by(NormalizedRecord.id.asc()).all()
    return (
        int(resolved_upload_id),
        resolved_normalization_run_id,
        record_count,
        normalized_records,
    )


def _compute_duplicate_groups(
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> tuple[int, int]:
    """Union-Find over the duplicate pairs to compute connected components.

    Returns (duplicate_group_count, affected_record_count).

    Example: pairs A-B, A-C, B-C → 1 group, 3 affected records.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is not None and right_id is not None and left_id != right_id:
            union(left_id, right_id)

    if not parent:
        return 0, 0

    groups: dict[int, set[int]] = {}
    for node in list(parent):
        root = find(node)
        groups.setdefault(root, set()).add(node)

    real_groups = {root: members for root, members in groups.items() if len(members) >= 2}
    return len(real_groups), sum(len(m) for m in real_groups.values())


def _persist_match_candidates(
    *,
    session,
    detection_run_id: int,
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> int:
    inserted = 0

    def _normalize_decision(value: Any) -> str:
        normalized = _safe_str(value).lower()
        if normalized in {"approved", "same_person"}:
            return "approved"
        if normalized in {"rejected", "different_person"}:
            return "rejected"
        return "pending"

    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is None or right_id is None or left_id == right_id:
            continue
        # Canonical ordering to prevent (A,B) and (B,A) duplicates.
        if left_id > right_id:
            left_id, right_id = right_id, left_id

        confidence = extract_confidence(payload)
        persisted_decision = _normalize_decision(
            payload.get("decision") or payload.get("finalDecision")
        )
        # Deduplicate within the same detection run (same pair can appear via multiple sources).
        existing = (
            session.query(MatchCandidate.id)
            .filter(MatchCandidate.detection_run_id == detection_run_id)
            .filter(MatchCandidate.left_id == left_id)
            .filter(MatchCandidate.right_id == right_id)
            .first()
        )
        if existing is not None:
            continue
        session.add(
            MatchCandidate(
                detection_run_id=detection_run_id,
                left_id=left_id,
                right_id=right_id,
                score=confidence,
                match_type=infer_match_type(payload),
                decision=persisted_decision,
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
    save_to_db: bool,
    job_id: int | None = None,
) -> dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id)
    session = SessionLocal()
    t_start = time.monotonic()

    logger.info(
        "[detect] Başlatıldı — uploadId=%s normalizationRunId=%s minRules=%s sessionId=%s",
        upload_id,
        normalization_run_id,
        min_rules_to_match,
        resolved_session_id,
    )

    try:
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=5,
            )

        (
            resolved_upload_id,
            resolved_normalization_run_id,
            record_count,
            normalized_records,
        ) = (
            _resolve_detection_scope_for_sync(
                session=session,
                upload_id=upload_id,
                normalization_run_id=normalization_run_id,
                max_records=DETECTION_SYNC_MAX_RECORDS,
            )
        )

        logger.info(
            "[detect] Analiz edilecek kayıt sayısı: %d (upload_id=%s, normalization_run_id=%s)",
            record_count,
            resolved_upload_id,
            resolved_normalization_run_id,
        )
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=20,
                total_rows=record_count,
                processed_rows=0,
            )

        detection_run = None
        detection_run_id: int | None = None
        if save_to_db:
            detection_run = DetectionRun(
                upload_id=resolved_upload_id,
                normalization_run_id=resolved_normalization_run_id,
                model_version=DEFAULT_MODEL_VERSION,
                threshold=DEFAULT_DETECTION_THRESHOLD,
            )
            session.add(detection_run)
            session.flush()
            detection_run_id = int(detection_run.id)
            logger.info("[detect] DetectionRun olusturuldu: id=%s", detection_run_id)
        else:
            logger.info("[detect] saveToDb=false; detection_run ve match_candidates yazilmayacak.")

        t_match = time.monotonic()
        df_clean, index_to_normalized_id = _build_matching_dataframe(normalized_records)
        duplicates, resolved_model_version = run_matching(
            df_clean=df_clean,
            min_rules_to_match=min_rules_to_match,
        )
        t_match_elapsed = time.monotonic() - t_match
        if detection_run is not None:
            detection_run.model_version = resolved_model_version

        candidate_pairs = int(getattr(duplicates, "candidate_pairs", len(duplicates)))
        candidate_pairs_limited = bool(
            getattr(duplicates, "candidate_pairs_limited", False)
        )
        duplicate_pairs = int(getattr(duplicates, "duplicate_pairs", len(duplicates)))
        logger.info(
            "[detect] Eşleştirme tamamlandı: %.2fs — model=%s — candidatePairs=%d duplicatePairs=%d",
            t_match_elapsed,
            resolved_model_version,
            candidate_pairs,
            duplicate_pairs,
        )
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=70,
                processed_rows=len(normalized_records),
            )

        inserted = 0
        if save_to_db and detection_run_id is not None:
            inserted = _persist_match_candidates(
                session=session,
                detection_run_id=detection_run_id,
                duplicates=list(duplicates),
                index_to_normalized_id=index_to_normalized_id,
            )
            logger.info("[detect] MatchCandidate kaydedildi: %d satir", inserted)
        else:
            logger.info("[detect] saveToDb=false; MatchCandidate insert atlandi.")
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=90,
                processed_rows=len(normalized_records),
            )

        # Connected-components: collapse pairs into groups (A-B + A-C + B-C = 1 group, 3 records)
        duplicate_group_count, affected_record_count = _compute_duplicate_groups(
            list(duplicates), index_to_normalized_id
        )
        logger.info(
            "[detect] Grup analizi: %d grup, %d etkilenen kayıt",
            duplicate_group_count,
            affected_record_count,
        )

        # Persist group metrics on the DetectionRun row
        if detection_run is not None:
            detection_run.duplicate_group_count = duplicate_group_count
            detection_run.affected_record_count = affected_record_count

        if save_to_db:
            session.commit()
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="completed",
                progress=100,
                processed_rows=len(normalized_records),
            )
            session.commit()

        t_total = time.monotonic() - t_start
        logger.info("[detect] Toplam süre: %.2fs", t_total)

        return {
            "sessionId": resolved_session_id,
            "jobId": job_id,
            "uploadId": resolved_upload_id,
            "normalizationRunId": resolved_normalization_run_id,
            "detectionRunId": detection_run_id,
            "candidatePairs": candidate_pairs,
            "candidatePairsLimited": candidate_pairs_limited,
            "duplicatePairs": duplicate_pairs,
            "duplicateGroupCount": duplicate_group_count,
            "affectedRecordCount": affected_record_count,
            "insertedRows": inserted,
            "totalRecords": record_count,
            "duplicates": list(duplicates),
        }
    except HTTPException:
        session.rollback()
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="failed",
                error_message="Detection failed with HTTPException",
            )
        raise
    except Exception as exc:
        session.rollback()
        logger.exception("[detect] Hata: %s", exc)
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="failed",
                error_message=str(exc),
            )
        raise HTTPException(
            status_code=500, detail=f"Tespit sırasında hata oluştu: {exc}"
        ) from exc
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
    job_id: int | None = None,
) -> dict[str, Any]:
    if normalization_run_id is not None or upload_id is not None:
        return run_detection_from_database(
            upload_id=upload_id,
            normalization_run_id=normalization_run_id,
            min_rules_to_match=min_rules_to_match,
            session_id=session_id,
            save_to_db=save_to_db,
            job_id=job_id,
        )

    raise HTTPException(
        status_code=400,
        detail="Mükerrer tespit için uploadId veya normalizationRunId zorunludur.",
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
    job_id: int | None = None,
) -> dict[str, Any]:
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
        save_to_db=save_to_db,
        job_id=job_id,
    )
