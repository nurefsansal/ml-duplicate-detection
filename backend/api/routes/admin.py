"""
Admin API Routes - Operatorun match'leri onaylamasi/reddetmesi
"""

from datetime import datetime
from typing import Any, Optional
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import AuditLog, Entity, EntityMap
from backend.services.database_service import EntityMapService
from backend.services.review_service import (
    MuhatapConflictError,
    approve_match_candidate,
    approve_group_partial,
    check_golden_muhatap_no_conflicts_for_entity,
    get_duplicate_groups_page,
    get_duplicate_groups,
    get_match_candidates,
    get_match_candidates_page,
    get_entity_memberships,
    get_match_candidate_statistics,
    merge_pending_into_entity,
    remove_confirmed_member_from_entity,
    get_pending_match_candidates,
    reject_match_candidate,
    remove_entity_membership,
    reset_match_candidate,
    serialize_match_candidate,
)
from backend.services.auth_service import get_current_user

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
logger = logging.getLogger(__name__)


def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(dependencies=[Depends(get_current_user)])


class PendingMatchResponse(BaseModel):
    """Beklemede olan match detaylari."""

    id: int
    left_id: int
    right_id: int
    decision: str = "pending"
    score: float
    match_type: str
    confidence: Optional[float]
    donor1_id: int
    donor2_id: int
    donor1_name: str
    donor1_email: Optional[str]
    donor1_phone: Optional[str] = None
    donor1_city: Optional[str] = None
    donor1_tc: Optional[str] = None
    donor2_name: str
    donor2_email: Optional[str]
    donor2_phone: Optional[str] = None
    donor2_city: Optional[str] = None
    donor2_tc: Optional[str] = None
    ml_score: float
    decision_reason: Optional[str]
    features: dict[str, Any]
    fieldComparisons: dict[str, Any] = Field(default_factory=dict)
    riskFlags: list[str] = Field(default_factory=list)
    ruleReasons: list[str] = Field(default_factory=list)
    decisionSource: str = "fallback_legacy"
    finalDecision: Optional[str] = None
    splinkMatchProbability: Optional[float] = None
    splinkMatchWeight: Optional[float] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ApproveMatchRequest(BaseModel):
    """Match onaylama istegi."""

    match_id: int
    approved_by: str = "admin"
    merge_into_entity: bool = True
    canonical_name: Optional[str] = None


class RejectMatchRequest(BaseModel):
    """Match reddetme istegi."""

    match_id: int
    rejected_by: str = "admin"
    reason: Optional[str] = None


class PartialApproveGroupRequest(BaseModel):
    """Duplicate group icinde kayit bazli karar istegi."""

    record_ids: list[int] = Field(default_factory=list)
    approved_record_ids: list[int] = Field(default_factory=list)
    rejected_record_ids: list[int] = Field(default_factory=list)
    upload_id: Optional[int] = None
    decision: Optional[str] = Field(default=None, pattern="^(pending|approved|rejected)$")
    note: Optional[str] = None
    golden_record_override: Optional[dict[str, Any]] = None
    co_review_acknowledged: bool = False


class MergeIntoEntityRequest(BaseModel):
    """Bekleyen gruptan mevcut onaylı entity'ye ekleme."""

    entity_id: int
    record_ids: list[int] = Field(default_factory=list)
    approved_record_ids: list[int] = Field(default_factory=list)
    upload_id: int
    note: Optional[str] = None
    golden_record_override: Optional[dict[str, Any]] = None
    co_review_acknowledged: bool = False


class RemoveMergeMemberRequest(BaseModel):
    upload_id: int
    """Entity canonical_data alanini guncelleme istegi."""

    fields: dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None


class ResetMatchRequest(BaseModel):
    """Eşleşme kararını geri alma."""

    reason: Optional[str] = None


@router.get("/admin/pending-matches")
def get_pending_matches(
    upload_id: Optional[int] = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = 50,
    different_muhatap_pair: bool = True,
    db: Session = Depends(get_db),
):
    """
    Henuz onaylanmamis match'leri listele.

    Query params:
    - upload_id: Belirli upload'a ait match'ler (opsiyonel)
    - limit: Kac adet goster (default 50)
    """
    try:
        total, pending_matches = get_match_candidates_page(
            db,
            upload_id=upload_id,
            decision="pending",
            page=page,
            page_size=page_size,
            latest_only=True,
            different_muhatap_pair=different_muhatap_pair,
        )
        result = [serialize_match_candidate(match, db) for match in pending_matches]

        return {
            "success": True,
            "count": len(result),
            "total": total,
            "page": max(1, int(page)),
            "page_size": max(1, min(200, int(page_size))),
            "total_pages": max(1, (total + max(1, min(200, int(page_size))) - 1) // max(1, min(200, int(page_size)))),
            "matches": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pending matches: {str(e)}")


@router.get("/matches")
def list_matches(
    decision: str = Query("pending", pattern="^(pending|approved|rejected)$"),
    upload_id: Optional[int] = None,
    limit: int = 100,
    page: int = 1,
    page_size: int = 50,
    different_muhatap_pair: bool = True,
    db: Session = Depends(get_db),
):
    """
    Match kayitlarini karar durumuna gore listele.

    Query params:
    - decision: pending | approved | rejected
    - upload_id: opsiyonel upload filtresi
    - limit: sonuc limiti
    """
    try:
        # Keep legacy "limit" behavior as an upper bound; pagination still applies.
        total, rows = get_match_candidates_page(
            db,
            upload_id=upload_id,
            decision=decision,
            page=page,
            page_size=min(int(page_size), int(limit)) if limit else page_size,
            latest_only=True,
            different_muhatap_pair=different_muhatap_pair,
        )
        result = [serialize_match_candidate(match, db) for match in rows]
        return {
            "success": True,
            "decision": decision,
            "count": len(result),
            "total": total,
            "page": max(1, int(page)),
            "page_size": max(1, min(200, int(page_size))),
            "total_pages": max(1, (total + max(1, min(200, int(page_size))) - 1) // max(1, min(200, int(page_size)))),
            "matches": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching matches: {str(e)}")


@router.get("/duplicate-groups")
def list_duplicate_groups(
    decision: str = Query("approved", pattern="^(pending|approved|rejected)$"),
    upload_id: Optional[int] = None,
    limit: int = 5000,
    page: int = 1,
    page_size: int = 50,
    different_muhatap_code: bool = True,
    db: Session = Depends(get_db),
):
    """
    Pair esitlesmeleri graph olarak birlestirip duplicate group listesi doner.
    """
    try:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))

        groups, total = get_duplicate_groups_page(
            db,
            upload_id=upload_id,
            decision=decision,
            limit=limit,
            page=page,
            page_size=page_size,
            different_muhatap_code=different_muhatap_code,
        )
        return {
            "success": True,
            "decision": decision,
            "count": len(groups),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "groups": groups,
        }
    except SQLAlchemyError as exc:
        logger.exception("Database error while fetching duplicate groups")
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "decision": decision,
                "count": 0,
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "groups": [],
                "error": "Duplicate group verisi okunurken veritabanı kaynaklı bir sorun oluştu.",
                "detail": str(getattr(exc, "orig", exc)),
            },
        )
    except Exception as e:
        logger.exception("Unexpected error while fetching duplicate groups")
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "decision": decision,
                "count": 0,
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "groups": [],
                "error": "Duplicate group verisi şu anda alınamadı.",
                "detail": str(e),
            },
        )


@router.post("/matches/group/{group_id}/partial-approve")
def partial_approve_group(
    group_id: str,
    request: PartialApproveGroupRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Duplicate group icinde kayit bazli confirmed / pending / excluded karari verir.
    """
    try:
        if not request.record_ids:
            raise HTTPException(
                status_code=400,
                detail="Kısmi onay için group içindeki record_ids bilgisi zorunludur.",
            )
        if request.upload_id is None:
            raise HTTPException(
                status_code=400,
                detail="Kısmi onay için seçili yükleme bilgisi (upload_id) zorunludur.",
            )
        result = approve_group_partial(
            db,
            group_id,
            request.approved_record_ids,
            request.rejected_record_ids,
            record_ids=request.record_ids,
            upload_id=request.upload_id,
            decision=request.decision,
            note=request.note,
            reviewed_by=current_user,
            golden_record_override=request.golden_record_override,
            co_review_acknowledged=bool(request.co_review_acknowledged),
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Grup bulunamadı. Runtime group_id yerine record_ids, upload_id ve "
                    "decision bilgileriyle tekrar deneyin."
                ),
            )

        db.commit()
        return result
    except MuhatapConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MUHATAP_CONFLICT",
                "proposed_muhatap": exc.proposed_muhatap,
                "conflicts": exc.conflicts,
            },
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error approving group: {str(e)}")


@router.post("/matches/group/{group_id}/merge-into-entity")
def merge_into_entity_route(
    group_id: str,
    request: MergeIntoEntityRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Bekleyen duplicate gruptan seçilen kayıtları mevcut onaylı entity ile birleştirir."""
    try:
        if not request.record_ids:
            raise HTTPException(
                status_code=400,
                detail="record_ids zorunludur.",
            )
        if not request.approved_record_ids:
            raise HTTPException(
                status_code=400,
                detail="approved_record_ids zorunludur.",
            )
        result = merge_pending_into_entity(
            db,
            entity_id=request.entity_id,
            group_id=group_id,
            record_ids=request.record_ids,
            approved_record_ids=request.approved_record_ids,
            upload_id=int(request.upload_id),
            golden_record_override=request.golden_record_override,
            note=request.note,
            reviewed_by=current_user,
            co_review_acknowledged=bool(request.co_review_acknowledged),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Entity bulunamadı.")
        db.commit()
        return result
    except MuhatapConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MUHATAP_CONFLICT",
                "proposed_muhatap": exc.proposed_muhatap,
                "conflicts": exc.conflicts,
            },
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Var olan gruba ekleme sırasında hata: {str(e)}",
        )


@router.post("/entities/{entity_id}/merge-members/{record_id}/remove")
def remove_merge_member_route(
    entity_id: int,
    record_id: int,
    request: RemoveMergeMemberRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Onaylı birleşik golden gruptan tek bir kaydı çıkarır."""
    try:
        result = remove_confirmed_member_from_entity(
            db,
            entity_id=int(entity_id),
            normalized_record_id=int(record_id),
            upload_id=int(request.upload_id),
            reviewed_by=current_user,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Entity bulunamadı.")
        db.commit()
        return {"success": True, **result}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Üyelik kaldırılırken hata: {str(e)}",
        )


@router.post("/admin/approve-match")
def approve_match(
    request: ApproveMatchRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Match'i onayla ve opsiyonel olarak entity'ye birlestir.
    """
    try:
        match, entity = approve_match_candidate(
            db,
            match_id=request.match_id,
            approved_by=current_user,
            merge_into_entity=request.merge_into_entity,
            canonical_name=request.canonical_name,
        )

        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        result = {
            "success": True,
            "match_id": match.id,
            "status": match.decision,
            "approved_by": current_user,
            "approved_at": datetime.utcnow().isoformat(),
        }

        if entity is not None:
            result["entity_id"] = entity.id
            result["entity_name"] = entity.canonical_name
            result["donor_count"] = entity.donor_count

        db.commit()
        return result

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error approving match: {str(e)}")


@router.post("/admin/matches/{match_id}/reset")
def reset_match_decision(
    match_id: int,
    request: ResetMatchRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Onay veya red kararını geri alır; eşleşmeyi tekrar inceleme kuyruğuna alır.
    """
    try:
        match = reset_match_candidate(
            db,
            match_id=match_id,
            reason=request.reason,
            reset_by=current_user,
        )
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        db.commit()
        return {
            "success": True,
            "match_id": match.id,
            "status": match.decision,
            "reset_by": current_user,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error resetting match: {str(e)}")


@router.post("/admin/reject-match")
def reject_match(
    request: RejectMatchRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Match'i reddet.
    """
    try:
        match = reject_match_candidate(
            db,
            match_id=request.match_id,
            rejected_by=current_user,
            reason=request.reason,
        )

        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        db.commit()

        return {
            "success": True,
            "match_id": match.id,
            "status": match.decision,
            "rejected_by": current_user,
            "rejected_at": datetime.utcnow().isoformat(),
            "reason": request.reason,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error rejecting match: {str(e)}")


@router.get("/admin/match-statistics")
def get_match_statistics(
    upload_id: int,
    db: Session = Depends(get_db),
):
    """
    Upload'in match istatistikleri.
    """
    try:
        stats = get_match_candidate_statistics(db, upload_id)
        return {
            "success": True,
            "upload_id": upload_id,
            **stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching statistics: {str(e)}")


@router.get("/admin/entities")
def get_entities(
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Tum entity'leri (birlestirilmis kisileri) listele.
    """
    try:
        entities = db.query(Entity).order_by(Entity.created_at.desc()).limit(limit).all()

        result = []
        for entity in entities:
            result.append(
                {
                    "id": entity.id,
                    "canonical_name": entity.canonical_name,
                    "canonical_email": entity.canonical_email,
                    "canonical_phone": entity.canonical_phone,
                    "canonical_city": entity.canonical_city,
                    "canonical_muhatap_no": getattr(entity, "canonical_muhatap_no", None),
                    "donor_count": entity.donor_count,
                    "merged_count": entity.merged_count,
                    "confidence_score": entity.confidence_score,
                    "merged_by": entity.merged_by,
                    "merged_at": entity.merged_at.isoformat() if entity.merged_at else None,
                    "created_at": entity.created_at.isoformat() if entity.created_at else None,
                }
            )

        return {
            "success": True,
            "count": len(result),
            "entities": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching entities: {str(e)}")


@router.get("/admin/entity/{entity_id}")
def get_entity_donors(
    entity_id: int,
    db: Session = Depends(get_db),
):
    """
    Entity'ye bagli tum donor'lari goster.
    """
    try:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        donor_list = []
        memberships = get_entity_memberships(db, entity_id)
        if memberships:
            for membership in memberships:
                donor = membership.normalized_record
                if donor is None:
                    continue
                donor_list.append(
                    {
                        "id": donor.id,
                        "full_name": donor.clean_name,
                        "email": donor.clean_email,
                        "phone": donor.clean_phone,
                        "city": donor.clean_city,
                        "upload_id": donor.upload_id,
                        "tc": donor.clean_tc,
                        "clean_muhatap_no": getattr(donor, "clean_muhatap_no", None) or "",
                    }
                )
        else:
            donors = EntityMapService.get_entity_donors(db, entity_id)
            for donor in donors:
                donor_list.append(
                    {
                        "id": donor.id,
                        "full_name": donor.full_name,
                        "email": donor.email,
                        "phone": donor.phone,
                        "city": donor.city,
                        "upload_id": donor.upload_id,
                    }
                )

        return {
            "success": True,
            "entity": {
                "id": entity.id,
                "canonical_name": entity.canonical_name,
                "canonical_muhatap_no": getattr(entity, "canonical_muhatap_no", None),
                "donor_count": entity.donor_count,
            },
            "donors": donor_list,
        } 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching entity donors: {str(e)}")


@router.delete("/admin/entity/{entity_id}")
def delete_entity_mapping(
    entity_id: int,
    donor_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Donor'i entity'den cikar (soft delete).
    """
    try:
        removed_membership = remove_entity_membership(
            db,
            entity_id=entity_id,
            normalized_record_id=donor_id,
        )

        removed_legacy = 0
        if not removed_membership:
            entity_maps = db.query(EntityMap).filter(
                EntityMap.entity_id == entity_id,
                EntityMap.donor_id == donor_id,
            ).all()

            if not entity_maps:
                raise HTTPException(
                    status_code=404,
                    detail="Entity-Donor mapping not found",
                )

            for entity_map in entity_maps:
                EntityMapService.deactivate_entity_map(db, entity_map.id)
                removed_legacy += 1

        db.commit()

        return {
            "success": True,
            "message": (
                "Removed 1 mapping(s)"
                if removed_membership
                else f"Removed {removed_legacy} mapping(s)"
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error removing mapping: {str(e)}")


@router.patch("/entities/{entity_id}/golden-record")
def update_golden_record(
    entity_id: int,
    request: GoldenRecordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Entity canonical_data JSON alanini ve uyumlu canonical kolonlari gunceller.
    """
    allowed_fields = {
        "clean_name",
        "clean_tc",
        "clean_phone",
        "clean_email",
        "clean_city",
        "clean_address",
        "clean_muhatap_no",
    }
    try:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")

        updates = {
            key: value
            for key, value in request.fields.items()
            if key in allowed_fields
        }
        if not updates:
            raise HTTPException(status_code=400, detail="No valid golden record fields")

        canonical_data = dict(entity.canonical_data or {})
        canonical_data.update({key: str(value).strip() if value is not None else "" for key, value in updates.items()})
        proposed_muhatap = str(canonical_data.get("clean_muhatap_no") or "").strip()
        if "clean_muhatap_no" in updates and proposed_muhatap:
            check_golden_muhatap_no_conflicts_for_entity(db, int(entity_id), proposed_muhatap)
        entity.canonical_data = canonical_data
        entity.canonical_name = canonical_data.get("clean_name") or entity.canonical_name
        entity.canonical_tc = canonical_data.get("clean_tc") or None
        entity.canonical_phone = canonical_data.get("clean_phone") or None
        entity.canonical_email = canonical_data.get("clean_email") or None
        entity.canonical_city = canonical_data.get("clean_city") or None
        entity.canonical_muhatap_no = canonical_data.get("clean_muhatap_no") or None
        entity.updated_at = datetime.utcnow()

        db.add(
            AuditLog(
                action_type="golden_record_update",
                entity_type="entity",
                entity_id=entity.id,
                payload={
                    "updated_fields": sorted(updates.keys()),
                    "fields": updates,
                    "note": request.note,
                },
                created_by=current_user,
            )
        )
        db.commit()
        return {
            "success": True,
            "entity_id": entity.id,
            "canonical_data": entity.canonical_data,
            "golden_record_id": entity.golden_record_id,
        }
    except MuhatapConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MUHATAP_CONFLICT",
                "proposed_muhatap": exc.proposed_muhatap,
                "conflicts": exc.conflicts,
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating golden record: {str(e)}")


__all__ = ["router"]
