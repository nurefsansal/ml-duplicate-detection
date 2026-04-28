from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.services.auth_service import get_current_user
from backend.services.job_service import get_job

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


@router.get("/jobs/{job_id}")
def get_job_status(job_id: int, db: Session = Depends(get_db)):
    job = get_job(db, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} bulunamadı")
    return {
        "success": True,
        "job": {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "progress": float(job.progress or 0.0),
            "total_rows": int(job.total_rows or 0),
            "processed_rows": int(job.processed_rows or 0),
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        },
    }
