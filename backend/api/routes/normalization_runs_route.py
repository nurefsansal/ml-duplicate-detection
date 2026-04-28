"""
Normalization Runs API Route - upload_id üzerinden normalizasyon çalıştır.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

DEFAULT_PROFILE = "default_person_normalization_v1"


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


@router.post("/normalization-runs")
def create_normalization_run(
    payload: NormalizationRunRequest,
    db: Session = Depends(get_db),
):
    """upload_id üzerinden raw_records normalize et, normalization_runs + normalized_records yaz."""
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

    raw_records = (
        db.query(RawRecord)
        .filter(RawRecord.upload_id == payload.upload_id)
        .order_by(RawRecord.id.asc())
        .all()
    )
    if not raw_records:
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
            progress=10,
            total_rows=len(raw_records),
            processed_rows=0,
        )
        db.flush()

    rows = [r.raw_payload for r in raw_records]
    df_original = pd.DataFrame(rows)

    if payload.column_mappings:
        rename_map: dict[str, str] = {}
        for mapping_item in payload.column_mappings:
            canonical = TARGET_TO_COLUMN.get(mapping_item.target_field)
            if canonical:
                rename_map[mapping_item.source_column] = canonical
        if rename_map:
            df_original = df_original.rename(columns=rename_map)
        df_processing = df_original
    else:
        try:
            df_processing = canonicalize_upload_dataframe(df_original)
        except Exception:
            df_processing = df_original

    try:
        normalized_df = prepare_normalized_dataframe(df_processing)
    except Exception as exc:
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=f"Normalizasyon hatası: {exc}",
            )
            db.commit()
        raise HTTPException(
            status_code=500, detail=f"Normalizasyon hatası: {exc}"
        ) from exc

    total_processed = len(raw_records)
    success_count = int(normalized_df["is_valid"].fillna(False).sum()) if total_processed else 0
    failed_count = total_processed - success_count

    try:
        normalization_run = NormalizationRun(
            upload_id=payload.upload_id,
            mapping_id=payload.mapping_id,
            normalization_profile=DEFAULT_PROFILE,
            total_processed=total_processed,
            success_count=success_count,
            failed_count=failed_count,
        )
        db.add(normalization_run)
        db.flush()

        normalized_payloads = [_row_to_payload(row) for _, row in normalized_df.iterrows()]
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="running",
                progress=40,
                processed_rows=0,
            )

        for index, (raw_record, normalized_payload) in enumerate(
            zip(raw_records, normalized_payloads, strict=False), start=1
        ):
            clean_name = str(normalized_payload.get("clean_name", "") or "")
            first_name = str(normalized_payload.get("first_name", "") or "")
            last_name = str(normalized_payload.get("last_name", "") or "")
            if not first_name or not last_name:
                derived_fn, derived_ln = extract_first_last_name(clean_name)
                first_name = first_name or derived_fn
                last_name = last_name or derived_ln

            db.add(
                NormalizedRecord(
                    raw_id=raw_record.id,
                    upload_id=payload.upload_id,
                    normalization_run_id=normalization_run.id,
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
            )
            if job is not None and index % 1000 == 0:
                progress = 40 + (index / max(total_processed, 1)) * 50
                update_job_progress(
                    db,
                    job_id=job.id,
                    status="running",
                    progress=progress,
                    processed_rows=index,
                )

        now = datetime.now(UTC).replace(tzinfo=None)
        upload.processing_stage = "normalized"
        upload.status = "completed"
        upload.completed_at = now
        upload.updated_at = now

        db.commit()
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="completed",
                progress=100,
                processed_rows=total_processed,
            )
            db.commit()

        return {
            "success": True,
            "job_id": job.id if job is not None else None,
            "upload_id": payload.upload_id,
            "normalization_run_id": normalization_run.id,
            "total_processed": total_processed,
            "success_count": success_count,
            "failed_count": failed_count,
        }
    except Exception as exc:
        db.rollback()
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=f"Normalizasyon kaydedilemedi: {exc}",
            )
            db.commit()
        raise HTTPException(
            status_code=500, detail=f"Normalizasyon kaydedilemedi: {exc}"
        ) from exc


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
