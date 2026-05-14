"""
Reports API Routes - Gerçek veritabanı tablolarından rapor verileri.
"""

from __future__ import annotations

import os
import csv
import io
from datetime import datetime
from typing import Optional

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, joinedload, sessionmaker

from backend.models.database import (
    DetectionRun,
    MatchCandidate,
    NormalizationRun,
    NormalizedRecord,
    ReviewAction,
    Upload,
)
from backend.api.routes.normalized_records_route import build_clean_dataset_rows
from backend.services.review_service import get_duplicate_groups, get_duplicate_groups_page

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


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


router = APIRouter()


def _csv_response(
    rows: list[dict],
    *,
    filename: str,
    fieldnames: Optional[list[str]] = None,
) -> Response:
    output = io.StringIO()
    if not rows:
        rows = [{}]
    fn = fieldnames if fieldnames is not None else list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fn, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        line = {}
        for key in fn:
            val = row.get(key, "")
            if val is None:
                line[key] = ""
            elif isinstance(val, (dict, list)):
                line[key] = json.dumps(val, ensure_ascii=False)
            elif isinstance(val, str):
                line[key] = val
            else:
                line[key] = str(val)
        writer.writerow(line)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


MUHATAP_MERGE_DETAIL_CSV_FIELDS = [
    "row_type",
    "group_id",
    "entity_id",
    "group_score",
    "merge_report_line",
    "golden_clean_name",
    "golden_clean_muhatap_no",
    "golden_clean_tc",
    "golden_clean_phone",
    "golden_clean_email",
    "golden_clean_city",
    "golden_clean_address",
    "prior_record_id",
    "prior_raw_id",
    "prior_upload_id",
    "prior_batch_id",
    "prior_muhatap_effective",
    "prior_clean_name",
    "prior_clean_tc",
    "prior_clean_phone",
    "prior_clean_email",
    "prior_clean_city",
    "prior_clean_address",
    "prior_clean_muhatap_no",
    "prior_completeness_score",
    "prior_normalized_payload_json",
    "prior_raw_payload_json",
]


def _golden_block_from_canonical(gr: dict) -> dict[str, str]:
    return {
        "golden_clean_name": gr.get("clean_name") or "",
        "golden_clean_muhatap_no": gr.get("clean_muhatap_no") or "",
        "golden_clean_tc": gr.get("clean_tc") or "",
        "golden_clean_phone": gr.get("clean_phone") or "",
        "golden_clean_email": gr.get("clean_email") or "",
        "golden_clean_city": gr.get("clean_city") or "",
        "golden_clean_address": gr.get("clean_address") or "",
    }


def _empty_prior_columns() -> dict[str, str]:
    return {
        "prior_record_id": "",
        "prior_raw_id": "",
        "prior_upload_id": "",
        "prior_batch_id": "",
        "prior_muhatap_effective": "",
        "prior_clean_name": "",
        "prior_clean_tc": "",
        "prior_clean_phone": "",
        "prior_clean_email": "",
        "prior_clean_city": "",
        "prior_clean_address": "",
        "prior_clean_muhatap_no": "",
        "prior_completeness_score": "",
        "prior_normalized_payload_json": "",
        "prior_raw_payload_json": "",
    }


def _rows_muhatap_merge_detail_long(groups: list[dict]) -> list[dict]:
    """Her grup: bir GOLDEN_RECORD satırı; ardından her önceki üye için PRIOR_MATCHED_MEMBER."""
    rows: list[dict] = []
    for group in groups:
        gr = group.get("golden_record") or {}
        snaps = gr.get("merged_member_snapshots") or []
        report = gr.get("merged_muhatap_report_line") or ""
        if not snaps and not report:
            continue
        gid = group.get("group_id") or ""
        eid = group.get("entity_id")
        score = group.get("group_score")
        golden_vals = _golden_block_from_canonical(gr)
        common = {
            "group_id": gid,
            "entity_id": "" if eid is None else str(eid),
            "group_score": "" if score is None else str(score),
            "merge_report_line": report,
        }
        rows.append(
            {
                "row_type": "GOLDEN_RECORD",
                **common,
                **golden_vals,
                **_empty_prior_columns(),
            }
        )
        for snap in snaps:
            np = snap.get("normalized_payload")
            rp = snap.get("raw_payload")
            rows.append(
                {
                    "row_type": "PRIOR_MATCHED_MEMBER",
                    **common,
                    **golden_vals,
                    "prior_record_id": str(snap.get("record_id") or ""),
                    "prior_raw_id": str(snap.get("raw_id") or ""),
                    "prior_upload_id": str(snap.get("upload_id") or ""),
                    "prior_batch_id": snap.get("batch_id") or "",
                    "prior_muhatap_effective": snap.get("muhatap_no_effective") or "",
                    "prior_clean_name": snap.get("clean_name") or "",
                    "prior_clean_tc": snap.get("clean_tc") or "",
                    "prior_clean_phone": snap.get("clean_phone") or "",
                    "prior_clean_email": snap.get("clean_email") or "",
                    "prior_clean_city": snap.get("clean_city") or "",
                    "prior_clean_address": snap.get("clean_address") or "",
                    "prior_clean_muhatap_no": snap.get("clean_muhatap_no") or "",
                    "prior_completeness_score": str(snap.get("completeness_score", "")),
                    "prior_normalized_payload_json": (
                        json.dumps(np, ensure_ascii=False) if isinstance(np, (dict, list)) else (np or "")
                    ),
                    "prior_raw_payload_json": (
                        json.dumps(rp, ensure_ascii=False) if isinstance(rp, (dict, list)) else (rp or "")
                    ),
                }
            )
    return rows


@router.get("/reports/overview")
def get_overview(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Genel özet: toplam upload, kayıt, tespit, onay istatistikleri."""
    try:
        dt_from = _parse_date(date_from)
        dt_to = _parse_date(date_to)

        upload_q = db.query(func.count(Upload.id))
        if dt_from:
            upload_q = upload_q.filter(Upload.created_at >= dt_from)
        if dt_to:
            upload_q = upload_q.filter(Upload.created_at <= dt_to)
        total_uploads = upload_q.scalar() or 0

        norm_q = db.query(func.count(NormalizedRecord.id))
        if dt_from:
            norm_q = norm_q.filter(NormalizedRecord.created_at >= dt_from)
        if dt_to:
            norm_q = norm_q.filter(NormalizedRecord.created_at <= dt_to)
        total_normalized = norm_q.scalar() or 0

        cand_base = db.query(MatchCandidate)
        if dt_from:
            cand_base = cand_base.filter(MatchCandidate.created_at >= dt_from)
        if dt_to:
            cand_base = cand_base.filter(MatchCandidate.created_at <= dt_to)

        total_candidates = cand_base.with_entities(func.count(MatchCandidate.id)).scalar() or 0
        approved = cand_base.filter(MatchCandidate.decision == "approved").with_entities(func.count(MatchCandidate.id)).scalar() or 0
        rejected = cand_base.filter(MatchCandidate.decision == "rejected").with_entities(func.count(MatchCandidate.id)).scalar() or 0
        pending = cand_base.filter(MatchCandidate.decision == "pending").with_entities(func.count(MatchCandidate.id)).scalar() or 0

        return {
            "success": True,
            "total_uploads": total_uploads,
            "total_normalized_records": total_normalized,
            "total_match_candidates": total_candidates,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/data-quality")
def get_data_quality(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Veri kalitesi: geçerli/geçersiz kayıt oranları, normalizasyon başarısı."""
    try:
        dt_from = _parse_date(date_from)
        dt_to = _parse_date(date_to)

        norm_rec_q = db.query(NormalizedRecord)
        if dt_from:
            norm_rec_q = norm_rec_q.filter(NormalizedRecord.created_at >= dt_from)
        if dt_to:
            norm_rec_q = norm_rec_q.filter(NormalizedRecord.created_at <= dt_to)

        total = norm_rec_q.with_entities(func.count(NormalizedRecord.id)).scalar() or 0
        valid = norm_rec_q.filter(NormalizedRecord.is_valid.is_(True)).with_entities(func.count(NormalizedRecord.id)).scalar() or 0
        invalid = total - valid
        tc_filled = norm_rec_q.filter(
            NormalizedRecord.clean_tc.isnot(None),
            NormalizedRecord.clean_tc != "",
        ).with_entities(func.count(NormalizedRecord.id)).scalar() or 0
        phone_filled = norm_rec_q.filter(
            NormalizedRecord.clean_phone.isnot(None),
            NormalizedRecord.clean_phone != "",
        ).with_entities(func.count(NormalizedRecord.id)).scalar() or 0
        email_filled = norm_rec_q.filter(
            NormalizedRecord.clean_email.isnot(None),
            NormalizedRecord.clean_email != "",
        ).with_entities(func.count(NormalizedRecord.id)).scalar() or 0

        runs_q = db.query(NormalizationRun)
        if dt_from:
            runs_q = runs_q.filter(NormalizationRun.created_at >= dt_from)
        if dt_to:
            runs_q = runs_q.filter(NormalizationRun.created_at <= dt_to)
        runs = runs_q.all()

        total_processed = sum(r.total_processed or 0 for r in runs)
        total_success = sum(r.success_count or 0 for r in runs)
        total_failed = sum(r.failed_count or 0 for r in runs)

        return {
            "success": True,
            "total_normalized_records": total,
            "valid_records": valid,
            "invalid_records": invalid,
            "validity_rate": round(valid / total * 100, 2) if total > 0 else 0,
            "normalization_runs": len(runs),
            "total_processed": total_processed,
            "total_success": total_success,
            "total_failed": total_failed,
            "tc_fill_rate": round(tc_filled / total * 100, 2) if total > 0 else 0,
            "phone_fill_rate": round(phone_filled / total * 100, 2) if total > 0 else 0,
            "email_fill_rate": round(email_filled / total * 100, 2) if total > 0 else 0,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/detection-summary")
def get_detection_summary(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Tespit özeti: detection_runs ve match_candidates istatistikleri."""
    try:
        dt_from = _parse_date(date_from)
        dt_to = _parse_date(date_to)

        runs_q = db.query(func.count(DetectionRun.id))
        if dt_from:
            runs_q = runs_q.filter(DetectionRun.created_at >= dt_from)
        if dt_to:
            runs_q = runs_q.filter(DetectionRun.created_at <= dt_to)
        total_runs = runs_q.scalar() or 0

        cand_q = db.query(MatchCandidate)
        if dt_from:
            cand_q = cand_q.filter(MatchCandidate.created_at >= dt_from)
        if dt_to:
            cand_q = cand_q.filter(MatchCandidate.created_at <= dt_to)

        total_candidates = cand_q.with_entities(func.count(MatchCandidate.id)).scalar() or 0
        approved = cand_q.filter(MatchCandidate.decision == "approved").with_entities(func.count(MatchCandidate.id)).scalar() or 0
        rejected = cand_q.filter(MatchCandidate.decision == "rejected").with_entities(func.count(MatchCandidate.id)).scalar() or 0
        pending = cand_q.filter(MatchCandidate.decision == "pending").with_entities(func.count(MatchCandidate.id)).scalar() or 0

        score_q = db.query(func.avg(MatchCandidate.score)).filter(MatchCandidate.score.isnot(None))
        if dt_from:
            score_q = score_q.filter(MatchCandidate.created_at >= dt_from)
        if dt_to:
            score_q = score_q.filter(MatchCandidate.created_at <= dt_to)
        avg_score_pct = round(float(score_q.scalar() or 0) * 100, 2)

        # Sum group metrics stored on detection_runs (NULL-safe with COALESCE)
        runs_for_group_q = db.query(
            func.sum(func.coalesce(DetectionRun.duplicate_group_count, 0)),
            func.sum(func.coalesce(DetectionRun.affected_record_count, 0)),
        )
        if dt_from:
            runs_for_group_q = runs_for_group_q.filter(DetectionRun.created_at >= dt_from)
        if dt_to:
            runs_for_group_q = runs_for_group_q.filter(DetectionRun.created_at <= dt_to)
        group_row = runs_for_group_q.one()
        total_duplicate_groups = int(group_row[0] or 0)
        total_affected_records = int(group_row[1] or 0)

        return {
            "success": True,
            "total_detection_runs": total_runs,
            "total_match_candidates": total_candidates,
            "total_duplicate_pairs": total_candidates,
            "total_duplicate_groups": total_duplicate_groups,
            "total_affected_records": total_affected_records,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "avg_score_pct": avg_score_pct,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/review-summary")
def get_review_summary(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """İnceleme özeti: review_actions istatistikleri."""
    try:
        dt_from = _parse_date(date_from)
        dt_to = _parse_date(date_to)

        q = db.query(ReviewAction)
        if dt_from:
            q = q.filter(ReviewAction.decided_at >= dt_from)
        if dt_to:
            q = q.filter(ReviewAction.decided_at <= dt_to)

        total_reviews = q.with_entities(func.count(ReviewAction.id)).scalar() or 0
        approvals = q.filter(ReviewAction.decision == "approved").with_entities(func.count(ReviewAction.id)).scalar() or 0
        rejections = q.filter(ReviewAction.decision == "rejected").with_entities(func.count(ReviewAction.id)).scalar() or 0
        recent_reviews = (
            q.options(joinedload(ReviewAction.match_candidate))
            .order_by(ReviewAction.decided_at.desc(), ReviewAction.id.desc())
            .limit(5)
            .all()
        )

        return {
            "success": True,
            "total_reviews": total_reviews,
            "approvals": approvals,
            "rejections": rejections,
            "recent_reviews": [
                {
                    "id": review.id,
                    "user": review.decided_by or "system",
                    "decision": review.decision,
                    "date": review.decided_at.isoformat() if review.decided_at else None,
                    "group_id": f"match_{review.match_id}",
                    "match_id": review.match_id,
                    "left_id": review.match_candidate.left_id if review.match_candidate else None,
                    "right_id": review.match_candidate.right_id if review.match_candidate else None,
                }
                for review in recent_reviews
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/upload-history")
def get_upload_history(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
):
    """Yükleme geçmişi: uploads tablosundan gerçek veri."""
    try:
        dt_from = _parse_date(date_from)
        dt_to = _parse_date(date_to)

        q = db.query(Upload)
        if dt_from:
            q = q.filter(Upload.created_at >= dt_from)
        if dt_to:
            q = q.filter(Upload.created_at <= dt_to)
        uploads = q.order_by(Upload.created_at.desc()).limit(limit).all()

        result = [
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
                    upload.completed_at.isoformat() if upload.completed_at else None
                ),
                "created_by": upload.created_by,
            }
            for upload in uploads
        ]

        return {"success": True, "count": len(result), "uploads": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/export/clean_dataset.csv")
def export_clean_dataset_csv(
    upload_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    rows = build_clean_dataset_rows(db, upload_id=upload_id)
    return _csv_response(rows, filename="clean_dataset.csv")


@router.get("/reports/export/approved_matches.csv")
def export_approved_matches_csv(
    upload_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(MatchCandidate).filter(MatchCandidate.decision == "approved")
    if upload_id is not None:
        query = query.join(DetectionRun).filter(DetectionRun.upload_id == upload_id)
    matches = query.order_by(MatchCandidate.created_at.desc()).all()
    rows = [
        {
            "match_id": match.id,
            "detection_run_id": match.detection_run_id,
            "left_id": match.left_id,
            "right_id": match.right_id,
            "score": match.score if match.score is not None else "",
            "confidence": match.confidence if match.confidence is not None else "",
            "match_type": match.match_type or "",
            "decision": match.decision or "",
            "created_at": match.created_at.isoformat() if match.created_at else "",
        }
        for match in matches
    ]
    return _csv_response(rows, filename="approved_matches.csv")


@router.get("/reports/export/duplicate_groups.csv")
def export_duplicate_groups_csv(
    upload_id: Optional[int] = None,
    decision: str = "approved",
    db: Session = Depends(get_db),
):
    groups = get_duplicate_groups(
        db,
        upload_id=upload_id,
        decision=decision,
        limit=50_000,
    )
    rows = [
        {
            "group_id": group["group_id"],
            "record_ids": ",".join(str(record_id) for record_id in group["record_ids"]),
            "record_count": len(group["record_ids"]),
            "group_score": group["group_score"],
            "group_score_max": group["group_score_max"],
            "match_count": group["match_count"],
        }
        for group in groups
    ]
    return _csv_response(rows, filename="duplicate_groups.csv")


@router.get("/reports/export/golden_records.csv")
def export_golden_records_csv(
    upload_id: Optional[int] = None,
    decision: str = "approved",
    db: Session = Depends(get_db),
):
    groups = get_duplicate_groups(
        db,
        upload_id=upload_id,
        decision=decision,
        limit=50_000,
    )
    rows = [
        {
            "group_id": group["group_id"],
            "record_count": len(group["record_ids"]),
            "group_score": group["group_score"],
            "clean_name": group["golden_record"].get("clean_name", ""),
            "clean_tc": group["golden_record"].get("clean_tc", ""),
            "clean_phone": group["golden_record"].get("clean_phone", ""),
            "clean_email": group["golden_record"].get("clean_email", ""),
            "clean_city": group["golden_record"].get("clean_city", ""),
            "clean_address": group["golden_record"].get("clean_address", ""),
            "clean_muhatap_no": group["golden_record"].get("clean_muhatap_no", ""),
            "merged_muhatap_report_line": group["golden_record"].get(
                "merged_muhatap_report_line", ""
            ),
            "merged_members_json": json.dumps(
                group["golden_record"].get("merged_member_snapshots") or [],
                ensure_ascii=False,
            ),
        }
        for group in groups
    ]
    return _csv_response(rows, filename="golden_records.csv")


@router.get("/reports/muhatap-merge-detail")
def get_muhatap_merge_report(
    upload_id: Optional[int] = None,
    decision: str = Query("approved", pattern="^(pending|approved|rejected)$"),
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """
    Farklı muhatap kodlu gruplar: golden + birleşim öncesi kayıt anlık görüntüleri (entity kaydından).
    """
    try:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        groups, total = get_duplicate_groups_page(
            db,
            upload_id=upload_id,
            decision=decision,
            limit=5000,
            page=page,
            page_size=page_size,
            different_muhatap_code=True,
        )
        out_groups: list[dict] = []
        for g in groups:
            gr = g.get("golden_record") or {}
            if not gr.get("merged_member_snapshots") and not gr.get("merged_muhatap_report_line"):
                continue
            out_groups.append(
                {
                    "group_id": g.get("group_id"),
                    "entity_id": g.get("entity_id"),
                    "muhatap_codes": g.get("muhatap_codes"),
                    "record_ids": g.get("record_ids"),
                    "group_score": g.get("group_score"),
                    "golden_record": gr,
                    "records": g.get("records"),
                }
            )
        return {
            "success": True,
            "decision": decision,
            "upload_id": upload_id,
            "total_all_groups": total,
            "count_with_merge_detail": len(out_groups),
            "page": page,
            "page_size": page_size,
            "groups": out_groups,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/reports/export/muhatap_merge_detail.csv")
def export_muhatap_merge_detail_csv(
    upload_id: Optional[int] = None,
    decision: str = Query("approved", pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
):
    """
    Farklı muhatap kodlu gruplarda birleşim raporu: her grup için GOLDEN_RECORD satırı,
    ardından birleşmeden önceki her üye için PRIOR_MATCHED_MEMBER satırı (tam alanlar + JSON).
    """
    groups = get_duplicate_groups(
        db,
        upload_id=upload_id,
        decision=decision,
        limit=50_000,
        different_muhatap_code=True,
    )
    rows = _rows_muhatap_merge_detail_long(groups)
    if not rows:
        rows = [
            {
                "row_type": "NO_DATA",
                "group_id": "",
                "entity_id": "",
                "group_score": "",
                "merge_report_line": (
                    "Bu yükleme ve filtre için birleşim detayı (onaylı golden + üye snapshot) "
                    "bulunamadı. Önce mükerrer kayıtlarda farklı muhatap kodlu bir grupta "
                    "Kaydet ile onaylayın."
                ),
                **_golden_block_from_canonical({}),
                **_empty_prior_columns(),
            }
        ]
    return _csv_response(
        rows,
        filename="muhatap_merge_detail.csv",
        fieldnames=MUHATAP_MERGE_DETAIL_CSV_FIELDS,
    )
