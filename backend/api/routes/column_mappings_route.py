"""
Column Mappings API Route - Kolon eşleştirme yönetimi.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import ColumnMapping, Upload

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

TARGET_FIELDS = ["name", "tc", "phone", "email", "city", "address", "other"]


class MappingItem(BaseModel):
    source_column: str
    target_field: str
    is_required: bool = False
    mapping_type: str = "direct"


class SaveColumnMappingsRequest(BaseModel):
    upload_id: int
    mappings: list[MappingItem]


@router.get("/column-mappings")
def get_column_mappings(
    upload_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Mevcut kolon eşleştirmelerini listele."""
    query = db.query(ColumnMapping)
    if upload_id is not None:
        query = query.filter(ColumnMapping.upload_id == upload_id)
    mappings = query.order_by(ColumnMapping.id.asc()).all()
    return {
        "success": True,
        "upload_id": upload_id,
        "count": len(mappings),
        "mappings": [
            {
                "id": m.id,
                "upload_id": m.upload_id,
                "source_column_name": m.source_column_name,
                "target_field_name": m.target_field_name,
                "is_required": m.is_required,
                "mapping_type": m.mapping_type,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ],
    }


@router.post("/column-mappings")
def save_column_mappings(
    payload: SaveColumnMappingsRequest,
    db: Session = Depends(get_db),
):
    """Kolon eşleştirmelerini kaydet (var olanları sil, yenilerini yaz)."""
    upload = db.query(Upload).filter(Upload.id == payload.upload_id).first()
    if not upload:
        raise HTTPException(
            status_code=404, detail=f"Upload {payload.upload_id} bulunamadı"
        )

    try:
        db.query(ColumnMapping).filter(
            ColumnMapping.upload_id == payload.upload_id
        ).delete()

        for item in payload.mappings:
            if not item.target_field or item.target_field == "other":
                continue
            db.add(
                ColumnMapping(
                    upload_id=payload.upload_id,
                    source_column_name=item.source_column,
                    target_field_name=item.target_field,
                    is_required=item.is_required,
                    mapping_type=item.mapping_type,
                )
            )

        db.commit()

        saved = (
            db.query(ColumnMapping)
            .filter(ColumnMapping.upload_id == payload.upload_id)
            .count()
        )
        return {"success": True, "upload_id": payload.upload_id, "saved": saved}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Eşleştirmeler kaydedilemedi: {exc}"
        ) from exc
