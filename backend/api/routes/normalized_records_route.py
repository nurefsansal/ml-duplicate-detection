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
from sqlalchemy.orm import Session, joinedload, sessionmaker

from backend.models.database import Entity, EntityMembership, NormalizedRecord

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
    "source",
    "source_label",
    "id",
    "entity_id",
    "record_id",
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
    "clean_muhatap_no",
    "is_valid",
    "blocking_key",
    "created_at",
]


def _serialize(record: NormalizedRecord) -> dict:
    return {
        "source": "normalized_record",
        "source_label": "Tekil Temiz Kayıt",
        "id": record.id,
        "entity_id": None,
        "record_id": record.id,
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
        "clean_muhatap_no": record.clean_muhatap_no or "",
        "is_valid": record.is_valid,
        "blocking_key": record.blocking_key or "",
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _entity_row(entity: Entity, confirmed_memberships: list[EntityMembership]) -> dict:
    canonical = entity.canonical_data if isinstance(entity.canonical_data, dict) else {}
    golden = entity.golden_record
    first_record = (
        golden
        or next(
            (
                membership.normalized_record
                for membership in confirmed_memberships
                if membership.normalized_record is not None
            ),
            None,
        )
    )

    upload_id = first_record.upload_id if first_record is not None else None
    normalization_run_id = (
        first_record.normalization_run_id if first_record is not None else None
    )
    record_id = first_record.id if first_record is not None else None
    clean_name = canonical.get("clean_name") or entity.canonical_name or ""
    clean_email = canonical.get("clean_email") or entity.canonical_email or ""
    clean_phone = canonical.get("clean_phone") or entity.canonical_phone or ""
    clean_tc = canonical.get("clean_tc") or entity.canonical_tc or ""
    clean_city = canonical.get("clean_city") or entity.canonical_city or ""
    clean_muhatap = (
        canonical.get("clean_muhatap_no")
        or getattr(entity, "canonical_muhatap_no", None)
        or ""
    )

    return {
        "source": "entity",
        "source_label": "Golden Record",
        "id": entity.id,
        "entity_id": entity.id,
        "record_id": record_id,
        "upload_id": upload_id,
        "normalization_run_id": normalization_run_id,
        "clean_name": clean_name,
        "first_name": canonical.get("first_name") or "",
        "last_name": canonical.get("last_name") or "",
        "clean_email": clean_email,
        "clean_phone": clean_phone,
        "clean_tc": clean_tc,
        "clean_city": clean_city,
        "clean_address": canonical.get("clean_address") or "",
        "clean_muhatap_no": clean_muhatap or "",
        "is_valid": bool(first_record.is_valid) if first_record is not None else True,
        "blocking_key": first_record.blocking_key if first_record is not None else "",
        "created_at": entity.updated_at.isoformat()
        if entity.updated_at
        else (entity.created_at.isoformat() if entity.created_at else None),
    }


def _row_matches_missing(row: dict, field_name: str, flag: Optional[bool]) -> bool:
    if flag is None:
        return True
    missing = not str(row.get(field_name) or "").strip()
    return missing if flag else not missing


def _row_matches_filters(
    row: dict,
    *,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    has_missing_tc: Optional[bool] = None,
    has_missing_phone: Optional[bool] = None,
    has_missing_email: Optional[bool] = None,
    has_missing_city: Optional[bool] = None,
) -> bool:
    if is_valid is not None and bool(row.get("is_valid")) is not is_valid:
        return False
    if search:
        term = search.lower()
        haystack = " ".join(
            str(row.get(field) or "")
            for field in (
                "clean_name",
                "clean_email",
                "clean_phone",
                "clean_tc",
                "clean_city",
                "clean_muhatap_no",
            )
        ).lower()
        if term not in haystack:
            return False
    return (
        _row_matches_missing(row, "clean_tc", has_missing_tc)
        and _row_matches_missing(row, "clean_phone", has_missing_phone)
        and _row_matches_missing(row, "clean_email", has_missing_email)
        and _row_matches_missing(row, "clean_city", has_missing_city)
    )


def build_clean_dataset_rows(
    db: Session,
    *,
    upload_id: Optional[int] = None,
    normalization_run_id: Optional[int] = None,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    has_missing_tc: Optional[bool] = None,
    has_missing_phone: Optional[bool] = None,
    has_missing_email: Optional[bool] = None,
    has_missing_city: Optional[bool] = None,
) -> list[dict]:
    confirmed_memberships = (
        db.query(EntityMembership)
        .options(
            joinedload(EntityMembership.entity).joinedload(Entity.golden_record),
            joinedload(EntityMembership.normalized_record),
        )
        .filter(EntityMembership.status == "confirmed")
        .all()
    )

    memberships_by_entity: dict[int, list[EntityMembership]] = {}
    confirmed_record_ids: set[int] = set()
    for membership in confirmed_memberships:
        record = membership.normalized_record
        if record is None:
            continue
        if upload_id is not None and record.upload_id != upload_id:
            continue
        if normalization_run_id is not None and record.normalization_run_id != normalization_run_id:
            continue
        memberships_by_entity.setdefault(int(membership.entity_id), []).append(membership)
        confirmed_record_ids.add(int(membership.normalized_record_id))

    rows: list[dict] = []
    for memberships in memberships_by_entity.values():
        entity = memberships[0].entity
        if entity is not None:
            rows.append(_entity_row(entity, memberships))

    query = db.query(NormalizedRecord)
    if upload_id is not None:
        query = query.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        query = query.filter(NormalizedRecord.normalization_run_id == normalization_run_id)
    if confirmed_record_ids:
        query = query.filter(~NormalizedRecord.id.in_(confirmed_record_ids))

    rows.extend(_serialize(record) for record in query.order_by(NormalizedRecord.id.asc()).all())
    rows = [
        row
        for row in rows
        if _row_matches_filters(
            row,
            is_valid=is_valid,
            search=search,
            has_missing_tc=has_missing_tc,
            has_missing_phone=has_missing_phone,
            has_missing_email=has_missing_email,
            has_missing_city=has_missing_city,
        )
    ]
    return sorted(rows, key=lambda row: (str(row.get("source") or ""), int(row.get("id") or 0)))


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
    """Temiz veri setini CSV, JSON veya XLSX olarak dışa aktar."""
    serialized = build_clean_dataset_rows(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
    )

    if format == "json":
        content = json.dumps(serialized, ensure_ascii=False, indent=2, default=str)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=clean_dataset.json"
            },
        )

    if format == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Clean Dataset"
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
                "Content-Disposition": "attachment; filename=clean_dataset.xlsx"
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
            "Content-Disposition": "attachment; filename=clean_dataset.csv"
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
    """Temiz veri setini listele: approved entity golden record + tekil normalized kayıtlar."""
    rows = build_clean_dataset_rows(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        is_valid=is_valid,
        search=search,
        has_missing_tc=has_missing_tc,
        has_missing_phone=has_missing_phone,
        has_missing_email=has_missing_email,
        has_missing_city=has_missing_city,
    )

    total = len(rows)
    offset = (page - 1) * page_size
    records = rows[offset : offset + page_size]

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "records": records,
    }
