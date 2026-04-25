from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.database_service import UploadService
from backend.services.mapping_service import _get_table_columns


def _json_safe_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            x = value.item()
            if isinstance(x, float) and pd.isna(x):
                return None
            return x
        except Exception:
            return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _json_safe_cell(v) for k, v in row.items()}


def rows_from_spreadsheet(filename: str, content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    name = (filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            raise ValueError("Sadece .xlsx, .xls ve .csv destekleniyor")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Dosya okunamadı: {exc}") from exc

    if df.empty:
        raise ValueError("Dosyada veri satırı yok")

    df.columns = [str(c).strip() for c in df.columns]
    records = df.to_dict(orient="records")
    out = [_row_to_payload(r) for r in records]
    source_columns = [str(c) for c in df.columns.tolist()]
    return out, source_columns


def ingest_file_to_raw_records(db: Session, filename: str, content: bytes) -> dict[str, Any]:
    rows, source_columns = rows_from_spreadsheet(filename, content)

    rec_cols = _get_table_columns(db, "raw_records")
    if not rec_cols or "upload_id" not in rec_cols:
        raise RuntimeError("raw_records tablosu bulunamadı veya upload_id kolonu eksik")

    payload_col = (
        "raw_payload"
        if "raw_payload" in rec_cols
        else "payload"
        if "payload" in rec_cols
        else None
    )
    if not payload_col:
        raise RuntimeError("raw_records içinde raw_payload veya payload kolonu gerekli")

    upload = UploadService.create_upload(
        db,
        file_name=filename or "upload",
        file_size_bytes=len(content),
        created_by="uploads_file_api",
    )
    upload_id = int(upload.id)
    UploadService.update_upload_status(db, upload_id, "processing")

    try:
        for row_payload in rows:
            payload_json = json.dumps(row_payload, sort_keys=True, default=str)
            ingestion_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

            fields: dict[str, Any] = {
                "upload_id": upload_id,
                payload_col: payload_json,
            }
            if "ingestion_hash" in rec_cols:
                fields["ingestion_hash"] = ingestion_hash
            if "row_status" in rec_cols:
                fields["row_status"] = "valid"
            if "validation_errors" in rec_cols:
                fields["validation_errors"] = json.dumps({})

            cols = list(fields.keys())
            stmt = text(
                f"INSERT INTO raw_records ({', '.join(cols)}) "
                f"VALUES ({', '.join(':' + c for c in cols)})"
            )
            db.execute(stmt, fields)

        UploadService.update_total_records(db, upload_id, len(rows))
        UploadService.update_upload_status(db, upload_id, "completed")
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "uploadId": upload_id,
        "fileName": filename or "",
        "totalRecords": len(rows),
        "sourceColumns": source_columns,
    }
