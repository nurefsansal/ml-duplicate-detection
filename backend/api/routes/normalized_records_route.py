"""
Normalized Records API Routes - Temiz veri seti CRUD ve export.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import NormalizedRecord

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


router = APIRouter()

_EXPORT_FIELDS = [
    "id",
    "upload_id",
    "normalization_run_id",
    "clean_name",
    "first_name",
    "last_name",
    "clean_email",
    "clean_phone",
    "clean_tc",
    "clean_city",
    "clean_address",
    "is_valid",
    "blocking_key",
    "created_at",
]


def _serialize(record: NormalizedRecord) -> dict:
    return {
        "id": record.id,
        "upload_id": record.upload_id,
        "normalization_run_id": record.normalization_run_id,
        "clean_name": record.clean_name or "",
        "first_name": record.first_name or "",
        "last_name": record.last_name or "",
        "clean_email": record.clean_email or "",
        "clean_phone": record.clean_phone or "",
        "clean_tc": record.clean_tc or "",
        "clean_city": record.clean_city or "",
        "clean_address": record.clean_address or "",
        "is_valid": record.is_valid,
        "blocking_key": record.blocking_key or "",
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _apply_missing_filter(query, field, flag: Optional[bool]):
    """flag=True → kayıt eksik; flag=False → kayıt mevcut."""
    if flag is None:
        return query
    if flag:
        return query.filter(or_(field.is_(None), field == ""))
    else:
        return query.filter(field.isnot(None), field != "")


@router.get("/normalized-records/export")
def export_normalized_records(
    upload_id: Optional[int] = None,
    normalization_run_id: Optional[int] = None,
    format: str = "csv",
    db: Session = Depends(get_db),
):
    """Normalize kayıtları CSV, JSON veya XLSX olarak dışa aktar."""
    query = db.query(NormalizedRecord)
    if upload_id is not None:
        query = query.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == normalization_run_id
        )

    records = query.order_by(NormalizedRecord.id.asc()).all()
    serialized = [_serialize(r) for r in records]

    if format == "json":
        content = json.dumps(serialized, ensure_ascii=False, indent=2, default=str)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=normalized_records.json"
            },
        )

    if format == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Normalized Records"
        ws.append(_EXPORT_FIELDS)
        for row in serialized:
            ws.append([row.get(f, "") for f in _EXPORT_FIELDS])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=normalized_records.xlsx"
            },
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(serialized)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=normalized_records.csv"
        },
    )


@router.get("/normalized-records/{record_id}")
def get_normalized_record(record_id: int, db: Session = Depends(get_db)):
    """Tek bir normalize kayıt detayı."""
    record = (
        db.query(NormalizedRecord)
        .filter(NormalizedRecord.id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "record": _serialize(record)}


@router.get("/normalized-records")
def list_normalized_records(
    upload_id: Optional[int] = None,
    normalization_run_id: Optional[int] = None,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    has_missing_tc: Optional[bool] = None,
    has_missing_phone: Optional[bool] = None,
    has_missing_email: Optional[bool] = None,
    has_missing_city: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """Normalize kayıtları listele (sayfalama + arama + filtreleme)."""
    query = db.query(NormalizedRecord)

    if upload_id is not None:
        query = query.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == normalization_run_id
        )
    if is_valid is not None:
        query = query.filter(NormalizedRecord.is_valid.is_(is_valid))
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                NormalizedRecord.clean_name.ilike(term),
                NormalizedRecord.clean_email.ilike(term),
                NormalizedRecord.clean_phone.ilike(term),
                NormalizedRecord.clean_tc.ilike(term),
                NormalizedRecord.clean_city.ilike(term),
            )
        )

    query = _apply_missing_filter(query, NormalizedRecord.clean_tc, has_missing_tc)
    query = _apply_missing_filter(query, NormalizedRecord.clean_phone, has_missing_phone)
    query = _apply_missing_filter(query, NormalizedRecord.clean_email, has_missing_email)
    query = _apply_missing_filter(query, NormalizedRecord.clean_city, has_missing_city)

    total = query.count()
    offset = (page - 1) * page_size
    records = (
        query.order_by(NormalizedRecord.id.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "records": [_serialize(r) for r in records],
    }
