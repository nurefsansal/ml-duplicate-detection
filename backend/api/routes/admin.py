"""
Admin API Routes - Operatorun match'leri onaylamasi/reddetmesi
"""

from typing import Any, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import Entity
from backend.services.database_service import (
    CompositeService,
    EntityMapService,
    EntityService,
    MatchService,
)

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


router = APIRouter()


class PendingMatchResponse(BaseModel):
    """Beklemede olan match detaylari."""

    id: int
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
    confidence: Optional[float]
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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unwrap_match_payload(value: Any) -> dict[str, Any]:
    payload = _safe_dict(value)
    if "features" in payload or "fieldComparisons" in payload:
        return payload
    return {"features": payload}


def _pick_donor_display_value(
    normalized_donor: Any,
    attribute: str,
    *,
    raw_attribute: str | None = None,
) -> Optional[str]:
    raw_donor = getattr(normalized_donor, "raw_donor", None)
    if raw_donor is not None and raw_attribute:
        raw_value = getattr(raw_donor, raw_attribute, None)
        if raw_value not in (None, ""):
            return str(raw_value)

    value = getattr(normalized_donor, attribute, None)
    if value in (None, ""):
        return None
    return str(value)


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
        pending_matches = MatchService.get_pending_matches(
            db,
            upload_id=upload_id,
            limit=limit,
        )

        result = []
        for match in pending_matches:
            payload = _unwrap_match_payload(match.features)
            features = _safe_dict(payload.get("features"))
            field_comparisons = _safe_dict(payload.get("fieldComparisons"))
            risk_flags = payload.get("riskFlags") if isinstance(payload.get("riskFlags"), list) else []
            rule_reasons = payload.get("ruleReasons") if isinstance(payload.get("ruleReasons"), list) else []

            result.append(
                {
                    "id": match.id,
                    "donor1_id": match.donor1_id,
                    "donor2_id": match.donor2_id,
                    "donor1_name": (
                        _pick_donor_display_value(match.donor1, "full_name", raw_attribute="full_name")
                        if match.donor1
                        else "N/A"
                    ),
                    "donor1_email": (
                        _pick_donor_display_value(match.donor1, "email", raw_attribute="email")
                        if match.donor1
                        else None
                    ),
                    "donor1_phone": (
                        _pick_donor_display_value(match.donor1, "phone", raw_attribute="phone")
                        if match.donor1
                        else None
                    ),
                    "donor1_city": (
                        _pick_donor_display_value(match.donor1, "city", raw_attribute="city")
                        if match.donor1
                        else None
                    ),
                    "donor1_tc": str(match.donor1.clean_tc) if match.donor1 and match.donor1.clean_tc else None,
                    "donor2_name": (
                        _pick_donor_display_value(match.donor2, "full_name", raw_attribute="full_name")
                        if match.donor2
                        else "N/A"
                    ),
                    "donor2_email": (
                        _pick_donor_display_value(match.donor2, "email", raw_attribute="email")
                        if match.donor2
                        else None
                    ),
                    "donor2_phone": (
                        _pick_donor_display_value(match.donor2, "phone", raw_attribute="phone")
                        if match.donor2
                        else None
                    ),
                    "donor2_city": (
                        _pick_donor_display_value(match.donor2, "city", raw_attribute="city")
                        if match.donor2
                        else None
                    ),
                    "donor2_tc": str(match.donor2.clean_tc) if match.donor2 and match.donor2.clean_tc else None,
                    "ml_score": match.ml_score,
                    "confidence": match.confidence,
                    "decision_reason": match.decision_reason,
                    "features": features,
                    "fieldComparisons": field_comparisons,
                    "riskFlags": risk_flags,
                    "ruleReasons": rule_reasons,
                    "decisionSource": str(payload.get("decisionSource", "fallback_legacy")),
                    "finalDecision": payload.get("finalDecision", match.decision_reason),
                    "splinkMatchProbability": payload.get("splinkMatchProbability", match.ml_score),
                    "splinkMatchWeight": payload.get("splinkMatchWeight"),
                    "created_at": match.created_at.isoformat() if match.created_at else None,
                }
            )

        return {
            "success": True,
            "count": len(result),
            "matches": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pending matches: {str(e)}")


@router.post("/admin/approve-match")
def approve_match(
    request: ApproveMatchRequest,
    db: Session = Depends(get_db),
):
    """
    Match'i onayla ve opsiyonel olarak entity'ye birlestir.
    """
    try:
        match = MatchService.approve_match(
            db,
            request.match_id,
            request.approved_by,
        )

        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        result = {
            "success": True,
            "match_id": match.id,
            "status": match.status,
            "approved_by": match.approved_by,
            "approved_at": match.approved_at.isoformat() if match.approved_at else None,
        }

        if request.merge_into_entity:
            canonical_name = request.canonical_name or f"{match.donor1.full_name} (Merged)"

            entity = CompositeService.merge_donors_to_entity(
                db,
                donor_ids=[match.donor1_id, match.donor2_id],
                canonical_name=canonical_name,
                canonical_email=match.donor1.email or match.donor2.email,
                canonical_phone=match.donor1.phone or match.donor2.phone,
                canonical_city=match.donor1.city or match.donor2.city,
                merged_by=request.approved_by,
                match_id=match.id,
            )

            result["entity_id"] = entity.id
            result["entity_name"] = entity.canonical_name
            result["donor_count"] = entity.donor_count

        db.commit()
        return result

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error approving match: {str(e)}")


@router.post("/admin/reject-match")
def reject_match(
    request: RejectMatchRequest,
    db: Session = Depends(get_db),
):
    """
    Match'i reddet.
    """
    try:
        match = MatchService.reject_match(
            db,
            request.match_id,
            request.reason,
            request.rejected_by,
        )

        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        db.commit()

        return {
            "success": True,
            "match_id": match.id,
            "status": match.status,
            "rejected_by": match.approved_by,
            "rejected_at": match.rejected_at.isoformat() if match.rejected_at else None,
            "reason": match.rejected_reason,
        }
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
        stats = MatchService.get_match_statistics(db, upload_id)
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
        entity = EntityService.get_entity(db, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        donors = EntityMapService.get_entity_donors(db, entity_id)

        donor_list = []
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
        from backend.models.database import EntityMap

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

        db.commit()

        return {
            "success": True,
            "message": f"Removed {len(entity_maps)} mapping(s)",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error removing mapping: {str(e)}")


__all__ = ["router"]
