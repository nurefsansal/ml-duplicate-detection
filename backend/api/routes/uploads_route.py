"""
Uploads API Route - Upload listesi + dosya yükleme (normalizasyonsuz).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import ColumnMapping, NormalizationRun, NormalizedRecord, RawRecord, Upload
from backend.services.normalization_service import SOURCE_FIELD_TARGETS

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


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


def _row_to_payload(row: dict) -> dict:
    return {str(k): _safe_val(v) for k, v in row.items()}


def _ingestion_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


router = APIRouter()


@router.post("/uploads/file")
async def upload_file_only(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Dosyayı yükle: uploads + raw_records oluştur. Normalizasyon YAPMA."""
    filename = (file.filename or "").lower()
    content = await file.read()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
            source_type = "excel"
        elif filename.endswith(".csv"):
            try:
                df = pd.read_csv(io.StringIO(content.decode("utf-8")))
            except UnicodeDecodeError:
                df = pd.read_csv(io.StringIO(content.decode("latin-1")))
            source_type = "csv"
        else:
            raise HTTPException(
                status_code=400,
                detail="Sadece .xlsx, .xls ve .csv dosyaları destekleniyor",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {exc}") from exc

    source_columns = [str(col) for col in df.columns]
    total_records = len(df)

    suggested_mappings = {
        col: SOURCE_FIELD_TARGETS.get(col.strip().lower(), "")
        for col in source_columns
    }

    try:
        upload = Upload(
            source_type=source_type,
            source_name=file.filename or "uploaded_file",
            file_name=file.filename or "uploaded_file",
            file_size_bytes=len(content),
            total_records=total_records,
            status="uploaded",
            processing_stage="raw",
        )
        db.add(upload)
        db.flush()

        for _, row in df.iterrows():
            raw_payload = _row_to_payload(row.to_dict())
            db.add(
                RawRecord(
                    upload_id=upload.id,
                    raw_payload=raw_payload,
                    ingestion_hash=_ingestion_hash(raw_payload),
                    row_status="pending",
                )
            )

        db.commit()
        db.refresh(upload)

        return {
            "success": True,
            "upload_id": upload.id,
            "file_name": upload.file_name,
            "source_type": upload.source_type,
            "total_records": total_records,
            "source_columns": source_columns,
            "suggested_mappings": suggested_mappings,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Upload kaydedilemedi: {exc}"
        ) from exc


@router.get("/uploads/{upload_id}/columns")
def get_upload_columns(upload_id: int, db: Session = Depends(get_db)):
    """Upload'ın ham kayıt kolon listesini döndür (ilk raw_record'dan)."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} bulunamadı")

    first_raw = (
        db.query(RawRecord).filter(RawRecord.upload_id == upload_id).first()
    )
    if not first_raw or not first_raw.raw_payload:
        return {
            "success": True,
            "upload_id": upload_id,
            "source_columns": [],
            "suggested_mappings": {},
        }

    source_columns = list(first_raw.raw_payload.keys())
    suggested_mappings = {
        col: SOURCE_FIELD_TARGETS.get(col.strip().lower(), "")
        for col in source_columns
    }

    return {
        "success": True,
        "upload_id": upload_id,
        "source_columns": source_columns,
        "suggested_mappings": suggested_mappings,
    }


@router.get("/uploads")
def list_uploads(
    limit: int = 50,
    has_normalized_records: bool = False,
    db: Session = Depends(get_db),
):
    """Upload listesi.

    has_normalized_records=true → sadece normalized_records tablosunda kaydı olan uploadları döner.
    Bu sayede Mükerrer Tespit dropdown'u sadece normalizasyon tamamlanmış uploadları gösterir.
    """
    try:
        q = db.query(Upload).order_by(Upload.created_at.desc())

        if has_normalized_records:
            upload_ids_with_records = [
                row[0]
                for row in db.query(NormalizedRecord.upload_id).distinct().all()
            ]
            if upload_ids_with_records:
                q = q.filter(Upload.id.in_(upload_ids_with_records))
            else:
                return {"success": True, "count": 0, "uploads": []}

        uploads = q.limit(limit).all()

        result = []
        for upload in uploads:
            latest_run = (
                db.query(NormalizationRun)
                .filter(NormalizationRun.upload_id == upload.id)
                .order_by(
                    NormalizationRun.created_at.desc(),
                    NormalizationRun.id.desc(),
                )
                .first()
            )
            result.append(
                {
                    "id": upload.id,
                    "file_name": upload.file_name,
                    "source_type": upload.source_type or "unknown",
                    "total_records": upload.total_records or 0,
                    "status": upload.status,
                    "processing_stage": upload.processing_stage,
                    "created_at": (
                        upload.created_at.isoformat() if upload.created_at else None
                    ),
                    "completed_at": (
                        upload.completed_at.isoformat()
                        if upload.completed_at
                        else None
                    ),
                    "latest_normalization_run_id": (
                        latest_run.id if latest_run else None
                    ),
                }
            )

        return {"success": True, "count": len(result), "uploads": result}
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error listing uploads: {exc}"
        ) from exc
