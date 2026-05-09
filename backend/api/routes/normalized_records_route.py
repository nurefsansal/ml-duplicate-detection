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
from sqlalchemy import and_, create_engine, exists, func, literal, or_
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


def _apply_normalized_record_filters(
    query,
    *,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    has_missing_tc: Optional[bool] = None,
    has_missing_phone: Optional[bool] = None,
    has_missing_email: Optional[bool] = None,
    has_missing_city: Optional[bool] = None,
):
    if is_valid is not None:
        query = query.filter(NormalizedRecord.is_valid.is_(is_valid))
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                NormalizedRecord.clean_name.ilike(term),
                NormalizedRecord.clean_email.ilike(term),
                NormalizedRecord.clean_phone.ilike(term),
                NormalizedRecord.clean_tc.ilike(term),
                NormalizedRecord.clean_city.ilike(term),
                NormalizedRecord.clean_muhatap_no.ilike(term),
            )
        )
    query = _apply_missing_filter(query, NormalizedRecord.clean_tc, has_missing_tc)
    query = _apply_missing_filter(query, NormalizedRecord.clean_phone, has_missing_phone)
    query = _apply_missing_filter(query, NormalizedRecord.clean_email, has_missing_email)
    query = _apply_missing_filter(query, NormalizedRecord.clean_city, has_missing_city)
    return query


def _apply_entity_filters(
    query,
    *,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    has_missing_tc: Optional[bool] = None,
    has_missing_phone: Optional[bool] = None,
    has_missing_email: Optional[bool] = None,
    has_missing_city: Optional[bool] = None,
):
    # Entity rows represent a "Golden Record". We filter using canonical_* columns.
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Entity.canonical_name.ilike(term),
                Entity.canonical_email.ilike(term),
                Entity.canonical_phone.ilike(term),
                Entity.canonical_tc.ilike(term),
                Entity.canonical_city.ilike(term),
                Entity.canonical_muhatap_no.ilike(term),
            )
        )
    query = _apply_missing_filter(query, Entity.canonical_tc, has_missing_tc)
    query = _apply_missing_filter(query, Entity.canonical_phone, has_missing_phone)
    query = _apply_missing_filter(query, Entity.canonical_email, has_missing_email)
    query = _apply_missing_filter(query, Entity.canonical_city, has_missing_city)

    # is_valid for entity rows is derived from golden_record when present; otherwise default True.
    if is_valid is not None:
        query = query.join(Entity.golden_record, isouter=True).filter(
            func.coalesce(NormalizedRecord.is_valid, literal(True)).is_(is_valid)
        )
    return query


def build_clean_dataset_page(
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
    page: int = 1,
    page_size: int = 50,
) -> tuple[int, list[dict]]:
    """
    DB-backed pagination for clean dataset rows.

    Order: entity rows first (source="entity", ordered by Entity.id),
    then remaining normalized records (source="normalized_record", ordered by NormalizedRecord.id).
    """
    page = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset = (page - 1) * page_size

    # Entities included: those with at least one confirmed membership (optionally scoped by upload/run).
    base_membership_q = (
        db.query(EntityMembership.entity_id)
        .join(NormalizedRecord, NormalizedRecord.id == EntityMembership.normalized_record_id)
        .filter(EntityMembership.status == "confirmed")
    )
    if upload_id is not None:
        base_membership_q = base_membership_q.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        base_membership_q = base_membership_q.filter(
            NormalizedRecord.normalization_run_id == normalization_run_id
        )
    eligible_entity_ids_sq = base_membership_q.distinct().subquery()

    entity_q = db.query(Entity).join(
        eligible_entity_ids_sq, eligible_entity_ids_sq.c.entity_id == Entity.id
    )
    entity_q = _apply_entity_filters(
        entity_q,
        is_valid=is_valid,
        search=search,
        has_missing_tc=has_missing_tc,
        has_missing_phone=has_missing_phone,
        has_missing_email=has_missing_email,
        has_missing_city=has_missing_city,
    )

    entity_total = int(entity_q.with_entities(func.count(Entity.id)).scalar() or 0)

    # Decide how much of this page comes from entities vs normalized records.
    entity_offset = min(offset, entity_total)
    entity_limit = max(0, min(page_size, entity_total - entity_offset))

    entity_rows: list[dict] = []
    if entity_limit > 0:
        # Pick one normalized_record per entity for upload_id/run_id + is_valid + blocking_key display.
        # Prefer Entity.golden_record when present, else use the smallest confirmed membership record id.
        min_membership_record_sq = (
            base_membership_q.with_entities(
                EntityMembership.entity_id.label("entity_id"),
                func.min(EntityMembership.normalized_record_id).label("min_record_id"),
            )
            .group_by(EntityMembership.entity_id)
            .subquery()
        )

        entities = (
            entity_q.options(joinedload(Entity.golden_record))
            .outerjoin(min_membership_record_sq, min_membership_record_sq.c.entity_id == Entity.id)
            .order_by(Entity.id.asc())
            .offset(entity_offset)
            .limit(entity_limit)
            .all()
        )

        # Bulk-load the fallback "first confirmed record" per entity (for display).
        entity_ids = [int(e.id) for e in entities]
        entity_min_rows = (
            db.query(
                min_membership_record_sq.c.entity_id,
                min_membership_record_sq.c.min_record_id,
            )
            .filter(min_membership_record_sq.c.entity_id.in_(entity_ids))
            .all()
        )
        entity_to_min_id = {
            int(entity_id): (int(min_id) if min_id is not None else None)
            for entity_id, min_id in entity_min_rows
        }
        fallback_ids = sorted({min_id for min_id in entity_to_min_id.values() if min_id is not None})
        fallback_by_id: dict[int, NormalizedRecord] = {}
        if fallback_ids:
            fallback_records = (
                db.query(NormalizedRecord)
                .filter(NormalizedRecord.id.in_(fallback_ids))
                .all()
            )
            fallback_by_id = {int(r.id): r for r in fallback_records}

        for e in entities:
            # reuse the existing serializer helper for consistency
            memberships: list[EntityMembership] = []
            # We only need a record for display; _entity_row also accepts empty list.
            # Provide a fake membership-like list with the chosen record to keep behavior stable.
            chosen = e.golden_record
            if chosen is None:
                min_id = entity_to_min_id.get(int(e.id))
                if min_id is not None:
                    chosen = fallback_by_id.get(int(min_id))
            if chosen is not None:
                temp = EntityMembership(entity_id=e.id, normalized_record_id=chosen.id, status="confirmed")
                temp.entity = e
                temp.normalized_record = chosen
                memberships = [temp]
            entity_rows.append(_entity_row(e, memberships))

    # Normalized records included: records NOT already confirmed into any entity (status=confirmed).
    normalized_offset = max(0, offset - entity_total)
    normalized_limit = max(0, page_size - len(entity_rows))

    normalized_rows: list[dict] = []
    if normalized_limit > 0:
        confirmed_exists = exists().where(
            and_(
                EntityMembership.normalized_record_id == NormalizedRecord.id,
                EntityMembership.status == "confirmed",
            )
        )
        norm_q = db.query(NormalizedRecord).filter(~confirmed_exists)
        if upload_id is not None:
            norm_q = norm_q.filter(NormalizedRecord.upload_id == upload_id)
        if normalization_run_id is not None:
            norm_q = norm_q.filter(NormalizedRecord.normalization_run_id == normalization_run_id)

        norm_q = _apply_normalized_record_filters(
            norm_q,
            is_valid=is_valid,
            search=search,
            has_missing_tc=has_missing_tc,
            has_missing_phone=has_missing_phone,
            has_missing_email=has_missing_email,
            has_missing_city=has_missing_city,
        )

        normalized_total = int(norm_q.with_entities(func.count(NormalizedRecord.id)).scalar() or 0)
        records = (
            norm_q.order_by(NormalizedRecord.id.asc())
            .offset(normalized_offset)
            .limit(normalized_limit)
            .all()
        )
        normalized_rows = [_serialize(r) for r in records]
    else:
        normalized_total = 0

    total = entity_total + normalized_total
    return total, [*entity_rows, *normalized_rows]


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
    total, records = build_clean_dataset_page(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        is_valid=is_valid,
        search=search,
        has_missing_tc=has_missing_tc,
        has_missing_phone=has_missing_phone,
        has_missing_email=has_missing_email,
        has_missing_city=has_missing_city,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "records": records,
    }
