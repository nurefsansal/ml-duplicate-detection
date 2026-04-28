"""
Admin API Routes - Operatorun match'leri onaylamasi/reddetmesi
"""

from datetime import datetime
from typing import Any, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import Entity, EntityMap
from backend.services.database_service import EntityMapService
from backend.services.review_service import (
    approve_match_candidate,
    get_duplicate_groups,
    get_match_candidates,
    get_entity_memberships,
    get_match_candidate_statistics,
    get_pending_match_candidates,
    reject_match_candidate,
    remove_entity_membership,
    serialize_match_candidate,
)
from backend.services.auth_service import get_current_user

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


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


@router.get("/admin/pending-matches")
def get_pending_matches(
    upload_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Henuz onaylanmamis match'leri listele.

    Query params:
    - upload_id: Belirli upload'a ait match'ler (opsiyonel)
    - limit: Kac adet goster (default 50)
    """
    try:
        pending_matches = get_pending_match_candidates(
            db,
            upload_id=upload_id,
            limit=limit,
        )

        result = [serialize_match_candidate(match) for match in pending_matches]

        return {
            "success": True,
            "count": len(result),
            "matches": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pending matches: {str(e)}")


@router.get("/matches")
def list_matches(
    decision: str = Query("pending", pattern="^(pending|approved|rejected)$"),
    upload_id: Optional[int] = None,
    limit: int = 100,
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
        matches = get_match_candidates(
            db,
            upload_id=upload_id,
            decision=decision,
            limit=limit,
        )
        result = [serialize_match_candidate(match) for match in matches]
        return {
            "success": True,
            "decision": decision,
            "count": len(result),
            "matches": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching matches: {str(e)}")


@router.get("/duplicate-groups")
def list_duplicate_groups(
    decision: str = Query("approved", pattern="^(pending|approved|rejected)$"),
    upload_id: Optional[int] = None,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """
    Pair esitlesmeleri graph olarak birlestirip duplicate group listesi doner.
    """
    try:
        groups = get_duplicate_groups(
            db,
            upload_id=upload_id,
            decision=decision,
            limit=limit,
        )
        return {
            "success": True,
            "decision": decision,
            "count": len(groups),
            "groups": groups,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching duplicate groups: {str(e)}")


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


__all__ = ["router"]
