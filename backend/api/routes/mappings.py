import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.schemas.requests import SaveColumnMappingsRequest
from backend.schemas.responses import ColumnMappingResponse, TargetFieldResponse
from backend.services.mapping_service import (
    get_mappings,
    get_target_fields,
    save_mappings,
    suggest_mappings,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/mappings/target-fields", response_model=TargetFieldResponse)
def mapping_target_fields():
    return {"fields": get_target_fields()}


@router.get("/mappings/{upload_id}", response_model=ColumnMappingResponse)
def read_mappings(upload_id: int, db: Session = Depends(get_db)):
    try:
        return get_mappings(db, upload_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mapping read failed: {exc}") from exc


@router.post("/mappings/{upload_id}/suggest", response_model=ColumnMappingResponse)
def suggest_upload_mappings(upload_id: int, db: Session = Depends(get_db)):
    try:
        return suggest_mappings(db, upload_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mapping suggestion failed: {exc}") from exc


@router.post("/mappings/{upload_id}", response_model=ColumnMappingResponse)
def upsert_upload_mappings(
    upload_id: int,
    payload: SaveColumnMappingsRequest,
    db: Session = Depends(get_db),
):
    try:
        mapping_payload = [mapping.model_dump() for mapping in payload.mappings]
        return save_mappings(
            db,
            upload_id=upload_id,
            mappings=mapping_payload,
            replace_existing=payload.replaceExisting,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mapping save failed: {exc}") from exc
