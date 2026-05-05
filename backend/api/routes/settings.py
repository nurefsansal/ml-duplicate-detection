from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import AppSettings
from backend.services.auth_service import get_current_user
from backend.services.scoring_app_settings import load_scoring_app_settings

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


class SettingUpsertRequest(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: Any


class SettingsBatchRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


def _upsert_setting(
    db: Session,
    *,
    key: str,
    value: Any,
    updated_by: str,
) -> AppSettings:
    normalized_key = key.strip()
    setting = db.query(AppSettings).filter(AppSettings.key == normalized_key).first()
    if setting is None:
        setting = AppSettings(
            key=normalized_key,
            value=value,
            updated_by=updated_by,
        )
        db.add(setting)
    else:
        setting.value = value
        setting.updated_by = updated_by
    return setting


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(AppSettings).order_by(AppSettings.key.asc()).all()
    return {row.key: row.value for row in rows}


@router.get("/settings/scoring")
def get_scoring_settings(db: Session = Depends(get_db)):
    """
    Tespit / karar motorunda kullanılan ağırlık ve olasılık eşikleri (0–100 yüzde).
    """
    weights, thresholds = load_scoring_app_settings(db)
    return {
        "weights": weights,
        "thresholds_percent": thresholds.as_percent_dict(),
    }


@router.post("/settings")
def save_setting(
    request: SettingUpsertRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    setting = _upsert_setting(
        db,
        key=request.key,
        value=request.value,
        updated_by=current_user,
    )
    db.commit()
    return {"success": True, "key": setting.key, "value": setting.value}


@router.post("/settings/batch")
def save_settings_batch(
    request: SettingsBatchRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    for key, value in request.settings.items():
        _upsert_setting(db, key=key, value=value, updated_by=current_user)
    db.commit()
    return {"success": True, "count": len(request.settings)}
