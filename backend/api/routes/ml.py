from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.services.auth_service import get_current_user
from backend.services.ml_service import get_model_status, train_match_probability_model

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


router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/ml/train")
def train_ml_model(
    db: Session = Depends(get_db),
):
    try:
        metrics = train_match_probability_model(db)
        return {"success": True, "metrics": metrics}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model eğitilemedi: {exc}") from exc


@router.get("/ml/status")
def ml_model_status():
    return {"success": True, **get_model_status()}
