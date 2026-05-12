"""
Normalized Records API Routes - Temiz veri seti CRUD ve export.
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections import defaultdict
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import and_, create_engine, exists, func, literal, or_
from sqlalchemy.orm import Session, joinedload, sessionmaker

from backend.models.database import (
    DetectionRun,
    Entity,
    EntityMembership,
    MatchCandidate,
    NormalizedRecord,
)
from backend.services.review_service import _build_golden_record, _record_completeness_score

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
    "merged_member_ids",
    "merge_type",
    "muhatap_values_before_merge",
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
        "merged_member_ids": "",
        "merge_type": "",
        "muhatap_values_before_merge": "",
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
    records_for_members = [
        m.normalized_record
        for m in confirmed_memberships
        if m.normalized_record is not None
    ]
    member_ids = sorted(int(r.id) for r in records_for_members)
    muhataps_before = sorted(
        {
            str(r.clean_muhatap_no or "").strip()
            for r in records_for_members
            if str(r.clean_muhatap_no or "").strip()
        }
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
        "merged_member_ids": ",".join(str(i) for i in member_ids),
        "merge_type": "entity",
        "muhatap_values_before_merge": "|".join(muhataps_before),
    }


def _uf_find(parents: dict[int, int], x: int) -> int:
    p = parents.get(x, x)
    if p != x:
        p = _uf_find(parents, p)
        parents[x] = p
    return parents.get(x, x)


def _uf_union(parents: dict[int, int], a: int, b: int) -> None:
    ra, rb = _uf_find(parents, a), _uf_find(parents, b)
    if ra != rb:
        parents[rb] = ra


def _approved_pair_merge_groups(
    db: Session,
    *,
    upload_id: Optional[int],
    normalization_run_id: Optional[int],
    excluded_record_ids: set[int],
) -> tuple[list[list[NormalizedRecord]], set[int]]:
    """
    Onaylı MatchCandidate kenarlarından bağlı bileşenler (>=2 kayıt).
    Entity üyeliği olan kayıtlar excluded_record_ids ile dışlanır.
    """
    q = (
        db.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.left_record),
            joinedload(MatchCandidate.right_record),
        )
        .join(DetectionRun, MatchCandidate.detection_run_id == DetectionRun.id)
        .filter(MatchCandidate.decision == "approved")
    )
    if upload_id is not None:
        q = q.filter(DetectionRun.upload_id == upload_id)
    if normalization_run_id is not None:
        q = q.filter(DetectionRun.normalization_run_id == normalization_run_id)

    parents: dict[int, int] = {}
    for mc in q.all():
        L, R = int(mc.left_id), int(mc.right_id)
        if L in excluded_record_ids or R in excluded_record_ids:
            continue
        lr, rr = mc.left_record, mc.right_record
        if lr is None or rr is None:
            continue
        if upload_id is not None and (
            int(lr.upload_id) != upload_id or int(rr.upload_id) != upload_id
        ):
            continue
        if normalization_run_id is not None:
            if (
                lr.normalization_run_id != normalization_run_id
                or rr.normalization_run_id != normalization_run_id
            ):
                continue
        parents.setdefault(L, L)
        parents.setdefault(R, R)
        _uf_union(parents, L, R)

    if not parents:
        return [], set()

    components: dict[int, list[int]] = defaultdict(list)
    for node in parents:
        components[_uf_find(parents, node)].append(node)

    group_ids = [sorted(ids) for ids in components.values() if len(ids) >= 2]
    if not group_ids:
        return [], set()

    flat = [i for g in group_ids for i in g]
    rec_by_id = {
        int(r.id): r
        for r in db.query(NormalizedRecord).filter(NormalizedRecord.id.in_(flat)).all()
    }
    groups: list[list[NormalizedRecord]] = []
    consumed: set[int] = set()
    for ids in group_ids:
        recs = [rec_by_id[i] for i in ids if i in rec_by_id]
        if len(recs) < 2:
            continue
        groups.append(recs)
        consumed.update(int(r.id) for r in recs)
    return groups, consumed


def _approved_merge_row(records: list[NormalizedRecord]) -> dict:
    golden = _build_golden_record(records)
    primary = sorted(
        records,
        key=lambda r: (_record_completeness_score(r), -int(r.id)),
        reverse=True,
    )[0]
    member_ids = sorted(int(r.id) for r in records)
    muhataps_before = sorted(
        {
            str(r.clean_muhatap_no or "").strip()
            for r in records
            if str(r.clean_muhatap_no or "").strip()
        }
    )
    return {
        "source": "approved_merge",
        "source_label": "Onaylı eşleşme birleşimi (Entity kaydı yok)",
        "id": primary.id,
        "entity_id": None,
        "record_id": primary.id,
        "upload_id": primary.upload_id,
        "normalization_run_id": primary.normalization_run_id,
        "clean_name": golden.get("clean_name", "") or "",
        "first_name": "",
        "last_name": "",
        "clean_email": golden.get("clean_email", "") or "",
        "clean_phone": golden.get("clean_phone", "") or "",
        "clean_tc": golden.get("clean_tc", "") or "",
        "clean_city": golden.get("clean_city", "") or "",
        "clean_address": golden.get("clean_address", "") or "",
        "clean_muhatap_no": golden.get("clean_muhatap_no", "") or "",
        "is_valid": all(r.is_valid for r in records),
        "blocking_key": primary.blocking_key or "",
        "created_at": None,
        "merged_member_ids": ",".join(str(i) for i in member_ids),
        "merge_type": "approved_merge",
        "muhatap_values_before_merge": "|".join(muhataps_before),
    }


def _clean_row_sort_key(row: dict) -> tuple[int, int]:
    src = row.get("source") or ""
    rank = {"entity": 0, "approved_merge": 1, "normalized_record": 2}.get(src, 9)
    return (rank, int(row.get("id") or 0))


def _segment_window(seg_start: int, seg_len: int, win_lo: int, win_hi: int) -> tuple[int, int]:
    a = max(seg_start, win_lo)
    b = min(seg_start + seg_len, win_hi)
    if b <= a:
        return 0, 0
    return a - seg_start, b - a


def _confirmed_entity_memberships_for_scope(
    db: Session,
    *,
    upload_id: Optional[int],
    normalization_run_id: Optional[int],
) -> tuple[dict[int, list[EntityMembership]], set[int]]:
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
    return memberships_by_entity, confirmed_record_ids


def build_merge_lineage_rows(
    db: Session,
    *,
    upload_id: Optional[int] = None,
    normalization_run_id: Optional[int] = None,
) -> list[dict]:
    """Önce/sonra denetim: Entity ve onaylı çift birleşimleri için üye ve muhatap özeti."""
    memberships_by_entity, confirmed_record_ids = _confirmed_entity_memberships_for_scope(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
    )
    out: list[dict] = []
    for memberships in memberships_by_entity.values():
        entity = memberships[0].entity
        if entity is None:
            continue
        records_for_members = [
            m.normalized_record
            for m in memberships
            if m.normalized_record is not None
        ]
        member_ids = sorted(int(r.id) for r in records_for_members)
        muhataps_before = sorted(
            {
                str(r.clean_muhatap_no or "").strip()
                for r in records_for_members
                if str(r.clean_muhatap_no or "").strip()
            }
        )
        names_before = sorted(
            {
                str(r.clean_name or "").strip()
                for r in records_for_members
                if str(r.clean_name or "").strip()
            }
        )
        row_display = _entity_row(entity, memberships)
        out.append(
            {
                "merge_kind": "entity",
                "entity_id": int(entity.id),
                "group_key": str(int(entity.id)),
                "member_normalized_ids": ",".join(str(i) for i in member_ids),
                "member_count": len(member_ids),
                "muhatap_values_before": "|".join(muhataps_before),
                "muhatap_value_after": str(row_display.get("clean_muhatap_no") or ""),
                "clean_name_values_before": "|".join(names_before),
                "clean_name_after": str(row_display.get("clean_name") or ""),
            }
        )

    merge_groups, _ = _approved_pair_merge_groups(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        excluded_record_ids=confirmed_record_ids,
    )
    for recs in merge_groups:
        if len(recs) < 2:
            continue
        golden = _build_golden_record(recs)
        member_ids = sorted(int(r.id) for r in recs)
        muhataps_before = sorted(
            {
                str(r.clean_muhatap_no or "").strip()
                for r in recs
                if str(r.clean_muhatap_no or "").strip()
            }
        )
        names_before = sorted(
            {
                str(r.clean_name or "").strip()
                for r in recs
                if str(r.clean_name or "").strip()
            }
        )
        out.append(
            {
                "merge_kind": "approved_merge",
                "entity_id": "",
                "group_key": f"approved-{member_ids[0]}",
                "member_normalized_ids": ",".join(str(i) for i in member_ids),
                "member_count": len(member_ids),
                "muhatap_values_before": "|".join(muhataps_before),
                "muhatap_value_after": str(golden.get("clean_muhatap_no") or ""),
                "clean_name_values_before": "|".join(names_before),
                "clean_name_after": str(golden.get("clean_name") or ""),
            }
        )

    return sorted(out, key=lambda r: (str(r.get("merge_kind") or ""), str(r.get("group_key") or "")))


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
    memberships_by_entity, confirmed_record_ids = _confirmed_entity_memberships_for_scope(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
    )

    rows: list[dict] = []
    for memberships in memberships_by_entity.values():
        entity = memberships[0].entity
        if entity is not None:
            rows.append(_entity_row(entity, memberships))

    merge_groups, merge_consumed = _approved_pair_merge_groups(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        excluded_record_ids=confirmed_record_ids,
    )
    for grp in merge_groups:
        if len(grp) >= 2:
            rows.append(_approved_merge_row(grp))

    query = db.query(NormalizedRecord)
    if upload_id is not None:
        query = query.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        query = query.filter(NormalizedRecord.normalization_run_id == normalization_run_id)
    exclude_ids = confirmed_record_ids | merge_consumed
    if exclude_ids:
        query = query.filter(~NormalizedRecord.id.in_(exclude_ids))

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
    return sorted(rows, key=_clean_row_sort_key)


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

    Order: Entity (golden) → onaylı eşleşme birleşimleri (Entity dışı) → kalan tekil kayıtlar.
    """
    page = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset = (page - 1) * page_size
    win_lo, win_hi = offset, offset + page_size

    _, confirmed_record_ids = _confirmed_entity_memberships_for_scope(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
    )
    merge_groups, merge_consumed = _approved_pair_merge_groups(
        db,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        excluded_record_ids=confirmed_record_ids,
    )
    approved_merge_rows_all = [
        _approved_merge_row(g) for g in merge_groups if len(g) >= 2
    ]
    approved_merge_rows = sorted(
        [
            row
            for row in approved_merge_rows_all
            if _row_matches_filters(
                row,
                is_valid=is_valid,
                search=search,
                has_missing_tc=has_missing_tc,
                has_missing_phone=has_missing_phone,
                has_missing_email=has_missing_email,
                has_missing_city=has_missing_city,
            )
        ],
        key=lambda r: int(r.get("id") or 0),
    )
    merge_total = len(approved_merge_rows)

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

    confirmed_exists = exists().where(
        and_(
            EntityMembership.normalized_record_id == NormalizedRecord.id,
            EntityMembership.status == "confirmed",
        )
    )
    norm_count_q = db.query(NormalizedRecord).filter(~confirmed_exists)
    if upload_id is not None:
        norm_count_q = norm_count_q.filter(NormalizedRecord.upload_id == upload_id)
    if normalization_run_id is not None:
        norm_count_q = norm_count_q.filter(
            NormalizedRecord.normalization_run_id == normalization_run_id
        )
    if merge_consumed:
        norm_count_q = norm_count_q.filter(~NormalizedRecord.id.in_(merge_consumed))
    norm_count_q = _apply_normalized_record_filters(
        norm_count_q,
        is_valid=is_valid,
        search=search,
        has_missing_tc=has_missing_tc,
        has_missing_phone=has_missing_phone,
        has_missing_email=has_missing_email,
        has_missing_city=has_missing_city,
    )
    normalized_total = int(
        norm_count_q.with_entities(func.count(NormalizedRecord.id)).scalar() or 0
    )

    skip_e, take_e = _segment_window(0, entity_total, win_lo, win_hi)
    skip_m, take_m = _segment_window(entity_total, merge_total, win_lo, win_hi)
    skip_n, take_n = _segment_window(
        entity_total + merge_total, normalized_total, win_lo, win_hi
    )

    entity_rows: list[dict] = []
    if take_e > 0:
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
            .offset(skip_e)
            .limit(take_e)
            .all()
        )
        entity_ids = [int(e.id) for e in entities]
        page_memberships = (
            db.query(EntityMembership)
            .options(joinedload(EntityMembership.normalized_record))
            .filter(
                EntityMembership.entity_id.in_(entity_ids),
                EntityMembership.status == "confirmed",
            )
            .all()
        )
        mem_by_entity: dict[int, list[EntityMembership]] = defaultdict(list)
        for m in page_memberships:
            rec = m.normalized_record
            if rec is None:
                continue
            if upload_id is not None and rec.upload_id != upload_id:
                continue
            if normalization_run_id is not None and rec.normalization_run_id != normalization_run_id:
                continue
            mem_by_entity[int(m.entity_id)].append(m)

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
            mems = mem_by_entity.get(int(e.id), [])
            if not mems:
                chosen = e.golden_record
                if chosen is None:
                    min_id = entity_to_min_id.get(int(e.id))
                    if min_id is not None:
                        chosen = fallback_by_id.get(int(min_id))
                if chosen is not None:
                    temp = EntityMembership(
                        entity_id=e.id, normalized_record_id=chosen.id, status="confirmed"
                    )
                    temp.entity = e
                    temp.normalized_record = chosen
                    mems = [temp]
            entity_rows.append(_entity_row(e, mems))

    merge_page_rows = (
        approved_merge_rows[skip_m : skip_m + take_m] if take_m > 0 else []
    )

    normalized_rows: list[dict] = []
    if take_n > 0:
        norm_q = db.query(NormalizedRecord).filter(~confirmed_exists)
        if upload_id is not None:
            norm_q = norm_q.filter(NormalizedRecord.upload_id == upload_id)
        if normalization_run_id is not None:
            norm_q = norm_q.filter(NormalizedRecord.normalization_run_id == normalization_run_id)
        if merge_consumed:
            norm_q = norm_q.filter(~NormalizedRecord.id.in_(merge_consumed))
        norm_q = _apply_normalized_record_filters(
            norm_q,
            is_valid=is_valid,
            search=search,
            has_missing_tc=has_missing_tc,
            has_missing_phone=has_missing_phone,
            has_missing_email=has_missing_email,
            has_missing_city=has_missing_city,
        )
        records = (
            norm_q.order_by(NormalizedRecord.id.asc())
            .offset(skip_n)
            .limit(take_n)
            .all()
        )
        normalized_rows = [_serialize(r) for r in records]

    total = entity_total + merge_total + normalized_total
    return total, [*entity_rows, *merge_page_rows, *normalized_rows]


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
