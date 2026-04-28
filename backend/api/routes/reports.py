"""
Reports API Routes - Gerçek veritabanı tablolarından rapor verileri.
"""

from __future__ import annotations

import os
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import (
    DetectionRun,
    MatchCandidate,
    NormalizationRun,
    NormalizedRecord,
    ReviewAction,
    Upload,
)
from backend.services.review_service import get_duplicate_groups

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


def _csv_response(rows: list[dict], *, filename: str) -> Response:
    output = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else []
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    if fieldnames:
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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

        return {
            "success": True,
            "total_reviews": total_reviews,
            "approvals": approvals,
            "rejections": rejections,
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
    query = db.query(NormalizedRecord)
    if upload_id is not None:
        query = query.filter(NormalizedRecord.upload_id == upload_id)
    records = query.order_by(NormalizedRecord.id.asc()).all()
    rows = [
        {
            "id": record.id,
            "upload_id": record.upload_id,
            "normalization_run_id": record.normalization_run_id,
            "clean_name": record.clean_name or "",
            "first_name": record.first_name or "",
            "last_name": record.last_name or "",
            "clean_tc": record.clean_tc or "",
            "clean_phone": record.clean_phone or "",
            "clean_email": record.clean_email or "",
            "clean_city": record.clean_city or "",
            "clean_address": record.clean_address or "",
            "clean_muhatap_no": record.clean_muhatap_no or "",
            "is_valid": bool(record.is_valid),
            "blocking_key": record.blocking_key or "",
            "created_at": record.created_at.isoformat() if record.created_at else "",
        }
        for record in records
    ]
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
        }
        for group in groups
    ]
    return _csv_response(rows, filename="golden_records.csv")
