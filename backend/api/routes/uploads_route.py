"""
Uploads API Route - Upload listesi + dosya yükleme (normalizasyonsuz).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import ColumnMapping, NormalizationRun, NormalizedRecord, RawRecord, Upload
from backend.services.normalization_service import infer_target_field_name

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


def _ensure_import_batch(db: Session, *, upload_id: int) -> str:
    batch_id = f"upload-{upload_id}"
    db.execute(
        text(
            """
            INSERT INTO import_batches (
                batch_id,
                source_name,
                source_type,
                status,
                record_count,
                created_at
            )
            SELECT
                :batch_id,
                uploads.file_name,
                COALESCE(uploads.source_type, 'unknown'),
                COALESCE(uploads.status, 'uploaded'),
                COALESCE(uploads.total_records, 0),
                COALESCE(uploads.created_at, CURRENT_TIMESTAMP)
            FROM uploads
            WHERE uploads.id = :upload_id
            ON CONFLICT (batch_id) DO NOTHING
            """
        ),
        {"batch_id": batch_id, "upload_id": upload_id},
    )
    return batch_id


def _suggested_target_field(source_column: str) -> str:
    target_field = infer_target_field_name(source_column)
    return "" if target_field == "ignored" else target_field


def _insert_raw_batch(
    db: Session,
    *,
    upload_id: int,
    rows: list[dict],
    start_index: int = 1,
) -> None:
    if not rows:
        return
    batch = []
    batch_id = _ensure_import_batch(db, upload_id=upload_id)
    for offset, row in enumerate(rows, start=start_index):
        payload = _row_to_payload(row)
        batch.append(
            RawRecord(
                upload_id=upload_id,
                batch_id=batch_id,
                row_index=offset,
                raw_payload=payload,
                ingestion_hash=_ingestion_hash(payload),
                row_status="pending",
            )
        )
    db.bulk_save_objects(batch)


def _iter_csv_chunks(file_path: str):
    try:
        return pd.read_csv(file_path, chunksize=2000, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(file_path, chunksize=2000, encoding="latin-1")


router = APIRouter()


@router.post("/uploads/file")
async def upload_file_only(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Dosyayı yükle: uploads + raw_records oluştur. Normalizasyon YAPMA."""
    filename = (file.filename or "").lower()
    if not (
        filename.endswith(".xlsx") or filename.endswith(".xls") or filename.endswith(".csv")
    ):
        raise HTTPException(
            status_code=400,
            detail="Sadece .xlsx, .xls ve .csv dosyaları destekleniyor",
        )

    temp_file_path: str | None = None
    file_size_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename or 'upload'}") as temp_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size_bytes += len(chunk)
                temp_file.write(chunk)
            temp_file_path = temp_file.name
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {exc}") from exc

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(temp_file_path)
            source_type = "excel"
            source_columns = [str(col) for col in df.columns]
            total_records = len(df)
            suggested_mappings = {col: _suggested_target_field(col) for col in source_columns}

            upload = Upload(
                source_type=source_type,
                source_name=file.filename or "uploaded_file",
                file_name=file.filename or "uploaded_file",
                file_size_bytes=file_size_bytes,
                total_records=total_records,
                status="uploaded",
                processing_stage="raw",
            )
            db.add(upload)
            db.flush()
            _insert_raw_batch(
                db,
                upload_id=upload.id,
                rows=[row.to_dict() for _, row in df.iterrows()],
                start_index=1,
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

        source_type = "csv"
        upload = Upload(
            source_type=source_type,
            source_name=file.filename or "uploaded_file",
            file_name=file.filename or "uploaded_file",
            file_size_bytes=file_size_bytes,
            total_records=0,
            status="uploaded",
            processing_stage="raw",
        )
        db.add(upload)
        db.flush()

        total_records = 0
        source_columns: list[str] = []
        batch_rows: list[dict] = []
        for chunk_df in _iter_csv_chunks(temp_file_path):
            if not source_columns:
                source_columns = [str(col) for col in chunk_df.columns]
            records = chunk_df.to_dict(orient="records")
            total_records += len(records)
            batch_rows.extend(records)
            if len(batch_rows) >= 2000:
                _insert_raw_batch(
                    db,
                    upload_id=upload.id,
                    rows=batch_rows,
                    start_index=total_records - len(batch_rows) + 1,
                )
                db.flush()
                batch_rows = []

        if batch_rows:
            _insert_raw_batch(
                db,
                upload_id=upload.id,
                rows=batch_rows,
                start_index=total_records - len(batch_rows) + 1,
            )

        if not source_columns:
            raise HTTPException(status_code=400, detail="CSV dosyası boş veya okunamadı")

        upload.total_records = total_records
        suggested_mappings = {col: _suggested_target_field(col) for col in source_columns}

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
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload kaydedilemedi: {exc}") from exc
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


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
        col: _suggested_target_field(col)
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
