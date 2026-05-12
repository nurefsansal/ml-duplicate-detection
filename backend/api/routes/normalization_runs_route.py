"""
Normalization Runs API Route - upload_id üzerinden normalizasyon çalıştır.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from backend.models.database import (
    ColumnMapping,
    NormalizationRun,
    NormalizedRecord,
    RawRecord,
    Upload,
)
from backend.services.normalization_service import (
    canonicalize_upload_dataframe,
    extract_first_last_name,
    prepare_normalized_dataframe,
)
from backend.services.job_service import create_job, update_job_progress
from backend.services.pipeline_log_service import (
    add_pipeline_event,
    create_pipeline_run,
    finalize_pipeline_run,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

DEFAULT_PROFILE = "default_person_normalization_v1"
NORMALIZATION_CHUNK_SIZE = int(os.getenv("NORMALIZATION_CHUNK_SIZE", "5000"))
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _safe_val(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def _row_to_payload(row: pd.Series | dict) -> dict:
    data = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    return {str(k): _safe_val(v) for k, v in data.items()}


def _iter_raw_record_chunks(
    db: Session,
    *,
    upload_id: int,
    chunk_size: int,
):
    last_id = 0
    while True:
        chunk = (
            db.query(RawRecord.id, RawRecord.raw_payload)
            .filter(RawRecord.upload_id == upload_id, RawRecord.id > last_id)
            .order_by(RawRecord.id.asc())
            .limit(chunk_size)
            .all()
        )
        if not chunk:
            break
        last_id = int(chunk[-1].id)
        yield chunk


def _apply_column_mappings(
    df_original: pd.DataFrame,
    column_mappings: Optional[list[ColumnMappingItem]],
) -> pd.DataFrame:
    if column_mappings:
        rename_map: dict[str, str] = {}
        for mapping_item in column_mappings:
            canonical = TARGET_TO_COLUMN.get(mapping_item.target_field)
            if canonical:
                rename_map[mapping_item.source_column] = canonical
        if rename_map:
            return df_original.rename(columns=rename_map)
        return df_original

    try:
        return canonicalize_upload_dataframe(df_original)
    except Exception:
        return df_original


def _build_normalized_record(
    *,
    raw_id: int,
    upload_id: int,
    normalization_run_id: int,
    normalized_payload: dict[str, Any],
) -> NormalizedRecord:
    clean_name = str(normalized_payload.get("clean_name", "") or "")
    first_name = str(normalized_payload.get("first_name", "") or "")
    last_name = str(normalized_payload.get("last_name", "") or "")
    if not first_name or not last_name:
        derived_fn, derived_ln = extract_first_last_name(clean_name)
        first_name = first_name or derived_fn
        last_name = last_name or derived_ln

    return NormalizedRecord(
        raw_id=raw_id,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        clean_name=clean_name,
        first_name=first_name,
        last_name=last_name,
        ordered_name=str(normalized_payload.get("ordered_name", "") or ""),
        name_phonetic=str(normalized_payload.get("name_phonetic", "") or ""),
        clean_phone=str(normalized_payload.get("clean_phone", "") or ""),
        phone_last7=str(normalized_payload.get("phone_last7", "") or ""),
        clean_email=str(normalized_payload.get("clean_email", "") or ""),
        clean_tc=str(normalized_payload.get("clean_tc", "") or ""),
        clean_city=str(normalized_payload.get("clean_city", "") or ""),
        clean_address=str(normalized_payload.get("clean_address", "") or ""),
        clean_muhatap_no=str(normalized_payload.get("clean_muhatap_no", "") or ""),
        blocking_key=str(normalized_payload.get("blocking_key", "") or ""),
        is_valid=bool(normalized_payload.get("is_valid", False)),
        normalized_payload=normalized_payload,
    )


class ColumnMappingItem(BaseModel):
    source_column: str
    target_field: str


class NormalizationRunRequest(BaseModel):
    upload_id: int
    mapping_id: Optional[int] = None
    column_mappings: Optional[list[ColumnMappingItem]] = None


router = APIRouter()

TARGET_TO_COLUMN = {
    "name": "Ad Soyad",
    "tc": "TC",
    "phone": "Telefon",
    "email": "E-mail",
    "city": "Şehir",
    "address": "Adres",
    "muhatap_no": "Muhatap No",
}


def column_mappings_are_actionable(items: Optional[list[ColumnMappingItem]]) -> bool:
    """En az bir kolon kanonik hedefe (TARGET_TO_COLUMN) eşlenmiş mi; 'other' sayılmaz."""
    if not items:
        return False
    return any(
        bool(item.target_field)
        and item.target_field != "other"
        and item.target_field in TARGET_TO_COLUMN
        for item in items
    )


def _load_saved_mappings(
    db: Session,
    *,
    upload_id: int,
    mapping_id: Optional[int],
) -> list[ColumnMapping]:
    """Kayıtlı kolon eşlemelerini döndürür.

    `mapping_id` verilmişse bu id'nin upload'a ait olduğunu doğrular; normalizasyon için
    yine de upload'daki *tüm* eşleme satırları kullanılır (tek satır = tek kolon çifti).
    """
    mappings = (
        db.query(ColumnMapping)
        .filter(ColumnMapping.upload_id == upload_id)
        .order_by(ColumnMapping.id.asc())
        .all()
    )
    if mapping_id is not None:
        selected = next((mapping for mapping in mappings if mapping.id == mapping_id), None)
        if selected is None:
            raise HTTPException(
                status_code=404,
                detail=f"Column mapping {mapping_id} upload {upload_id} için bulunamadı",
            )
    return mappings


def _build_rename_map_from_column_mappings(mappings: list[ColumnMapping]) -> dict[str, str]:
    rename_map: dict[str, str] = {}
    for mapping in mappings:
        canonical = TARGET_TO_COLUMN.get(mapping.target_field_name)
        if canonical:
            rename_map[mapping.source_column_name] = canonical
    return rename_map


@router.post("/normalization-runs")
def create_normalization_run(
    background_tasks: BackgroundTasks,
    request: Request,
    payload: NormalizationRunRequest,
    db: Session = Depends(get_db),
):
    """upload_id üzerinden raw_records normalize et (arka planda), normalization_runs + normalized_records yaz."""
    job = create_job(db, job_type="normalization")
    if job is not None:
        db.flush()
        db.commit()
    upload = db.query(Upload).filter(Upload.id == payload.upload_id).first()
    if not upload:
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=f"Upload {payload.upload_id} bulunamadı",
            )
            db.commit()
        raise HTTPException(
            status_code=404, detail=f"Upload {payload.upload_id} bulunamadı"
        )

    total_raw_records = (
        db.query(RawRecord.id)
        .filter(RawRecord.upload_id == payload.upload_id)
        .count()
    )
    if total_raw_records == 0:
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=f"Upload {payload.upload_id} için raw_record bulunamadı",
            )
            db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Upload {payload.upload_id} için raw_record bulunamadı",
        )
    if job is not None:
        update_job_progress(
            db,
            job_id=job.id,
            status="running",
            progress=1,
            total_rows=total_raw_records,
            processed_rows=0,
        )
        db.flush()

    saved_mappings: list[ColumnMapping] = []
    resolved_column_mappings: Optional[list[ColumnMappingItem]] = payload.column_mappings
    if resolved_column_mappings is None:
        saved_mappings = _load_saved_mappings(
            db,
            upload_id=payload.upload_id,
            mapping_id=payload.mapping_id,
        )
        if saved_mappings:
            resolved_column_mappings = [
                ColumnMappingItem(
                    source_column=mapping.source_column_name,
                    target_field=mapping.target_field_name,
                )
                for mapping in saved_mappings
            ]

    if not column_mappings_are_actionable(resolved_column_mappings):
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message="Geçerli kolon eşlemesi yok (en az bir hedef alan gerekli).",
            )
            db.commit()
        raise HTTPException(
            status_code=400,
            detail=(
                "En az bir kaynak kolonu hedef alana eşleştirin (ör. Ad Soyad, TC, Telefon). "
                "'Diğer' hedefi sayılmaz. Önce Kolon eşleştirmelerini kaydedin."
            ),
        )

    normalization_run = NormalizationRun(
        upload_id=payload.upload_id,
        mapping_id=payload.mapping_id
        if payload.mapping_id is not None
        else (saved_mappings[0].id if not payload.column_mappings and saved_mappings else None),
        normalization_profile=DEFAULT_PROFILE,
        total_processed=0,
        success_count=0,
        failed_count=0,
    )
    db.add(normalization_run)
    db.flush()
    run_id = int(normalization_run.id)
    db.commit()

    req_id = getattr(getattr(request, "state", None), "request_id", None)
    background_tasks.add_task(
        _run_normalization_job,
        upload_id=payload.upload_id,
        normalization_run_id=run_id,
        total_raw_records=total_raw_records,
        column_mappings=resolved_column_mappings,
        job_id=job.id if job is not None else None,
        request_id=req_id,
    )

    return {
        "success": True,
        "job_id": job.id if job is not None else None,
        "upload_id": payload.upload_id,
        "normalization_run_id": run_id,
        "total_processed": 0,
        "success_count": 0,
        "failed_count": 0,
    }


def _run_normalization_job(
    *,
    upload_id: int,
    normalization_run_id: int,
    total_raw_records: int,
    column_mappings: Optional[list[ColumnMappingItem]],
    job_id: int | None,
    request_id: str | None,
):
    db = SessionLocal()
    t_total = time.monotonic()
    run_log_id: int | None = None
    try:
        run_log = create_pipeline_run(
            db,
            pipeline_type="normalization",
            request_id=request_id,
            upload_id=upload_id,
            job_id=job_id,
            normalization_run_id=normalization_run_id,
            metadata={"chunk_size": NORMALIZATION_CHUNK_SIZE},
        )
        run_log_id = run_log.id
        add_pipeline_event(
            db,
            run_id=run_log.id,
            stage="standardize",
            event_type="started",
            message="Standardizasyon başladı",
            total_rows=total_raw_records,
        )
        db.commit()

        normalization_run = db.query(NormalizationRun).filter(NormalizationRun.id == normalization_run_id).first()
        upload = db.query(Upload).filter(Upload.id == upload_id).first()
        if normalization_run is None or upload is None:
            raise RuntimeError("NormalizationRun veya Upload bulunamadı")

        total_processed = 0
        success_count = 0
        failed_count = 0

        for chunk_index, raw_chunk in enumerate(
            _iter_raw_record_chunks(db, upload_id=upload_id, chunk_size=NORMALIZATION_CHUNK_SIZE),
            start=1,
        ):
            t_chunk = time.monotonic()
            raw_ids = [int(row.id) for row in raw_chunk]
            rows = [row.raw_payload for row in raw_chunk]
            df_original = pd.DataFrame(rows)
            df_processing = _apply_column_mappings(df_original, column_mappings)

            normalized_df = prepare_normalized_dataframe(df_processing)

            normalized_payloads = [_row_to_payload(row) for row in normalized_df.to_dict(orient="records")]
            normalized_objects = [
                _build_normalized_record(
                    raw_id=raw_id,
                    upload_id=upload_id,
                    normalization_run_id=normalization_run_id,
                    normalized_payload=normalized_payload,
                )
                for raw_id, normalized_payload in zip(raw_ids, normalized_payloads, strict=False)
            ]

            if normalized_objects:
                db.bulk_save_objects(normalized_objects)

            chunk_processed = len(raw_ids)
            chunk_success = (
                int(normalized_df["is_valid"].fillna(False).sum())
                if chunk_processed and "is_valid" in normalized_df.columns
                else 0
            )
            chunk_failed = chunk_processed - chunk_success
            total_processed += chunk_processed
            success_count += chunk_success
            failed_count += chunk_failed

            normalization_run.total_processed = total_processed
            normalization_run.success_count = success_count
            normalization_run.failed_count = failed_count

            if job_id is not None:
                progress = (total_processed / max(total_raw_records, 1)) * 100.0
                update_job_progress(
                    db,
                    job_id=job_id,
                    status="running",
                    progress=progress,
                    processed_rows=total_processed,
                )

            if run_log_id is not None:
                finalize_pipeline_run(
                    db,
                    run_id=run_log_id,
                    status="running",
                    total_rows=total_raw_records,
                    processed_rows=total_processed,
                )

            db.commit()
            logger.info(
                "Normalization chunk completed upload_id=%s run_id=%s chunk=%s processed=%s success=%s failed=%s elapsed=%.2fs",
                upload_id,
                normalization_run_id,
                chunk_index,
                chunk_processed,
                chunk_success,
                chunk_failed,
                time.monotonic() - t_chunk,
            )

            raw_ids.clear()
            rows.clear()
            normalized_payloads.clear()
            normalized_objects.clear()
            del raw_chunk, df_original, df_processing, normalized_df
            gc.collect()

        now = datetime.now(UTC).replace(tzinfo=None)
        upload.processing_stage = "normalized"
        upload.status = "completed"
        upload.completed_at = now
        upload.updated_at = now

        if job_id is not None:
            update_job_progress(
                db,
                job_id=job_id,
                status="completed",
                progress=100,
                processed_rows=total_processed,
            )

        if run_log_id is not None:
            duration_ms = int((time.monotonic() - t_total) * 1000)
            add_pipeline_event(
                db,
                run_id=run_log_id,
                stage="standardize",
                event_type="completed",
                message="Standardizasyon tamamlandı",
                total_rows=total_raw_records,
                processed_rows=total_processed,
                error_count=failed_count,
                duration_ms=duration_ms,
            )
            finalize_pipeline_run(
                db,
                run_id=run_log_id,
                status="completed",
                total_rows=total_raw_records,
                processed_rows=total_processed,
                error_count=failed_count,
                metadata_patch={"duration_ms": duration_ms},
            )

        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if job_id is not None:
            update_job_progress(db, job_id=job_id, status="failed", error_message=str(exc))
        if run_log_id is not None:
            add_pipeline_event(db, run_id=run_log_id, stage="standardize", event_type="failed", message=str(exc))
            finalize_pipeline_run(db, run_id=run_log_id, status="failed", error_message=str(exc))
        db.commit()
    finally:
        db.close()

@router.get("/normalization-runs")
def list_normalization_runs(
    upload_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Normalizasyon çalışma listesi."""
    query = db.query(NormalizationRun)
    if upload_id is not None:
        query = query.filter(NormalizationRun.upload_id == upload_id)
    runs = query.order_by(NormalizationRun.id.desc()).limit(limit).all()
    return {
        "success": True,
        "count": len(runs),
        "runs": [
            {
                "id": r.id,
                "upload_id": r.upload_id,
                "normalization_profile": r.normalization_profile,
                "total_processed": r.total_processed,
                "success_count": r.success_count,
                "failed_count": r.failed_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }
