from __future__ import annotations

import csv
import io
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.services.auth_service import get_current_user
from backend.services.ml_feature_schema import CANONICAL_ML_MODEL_FEATURE_COLUMNS
from backend.services.ml_service import get_model_status, train_match_probability_model
from backend.services.review_service import collect_ground_truth_labeled_rows

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


@router.get("/ml/ground-truth.csv")
def export_match_ground_truth_csv(db: Session = Depends(get_db)):
    """
    CSV of approved/rejected pairs with canonical 6-column ML features (train=inference schema).
    """
    rows = collect_ground_truth_labeled_rows(db)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Etiketli onay/red eşleşmesi yok; önce inceleme kararı verin.",
        )
    buf = io.StringIO()
    fieldnames = [
        "match_id",
        "left_id",
        "right_id",
        "upload_id",
        "detection_run_id",
        "label",
        "confidence",
        *CANONICAL_ML_MODEL_FEATURE_COLUMNS,
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    payload = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="match_ground_truth.csv"',
        },
    )
