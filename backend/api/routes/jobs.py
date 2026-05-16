from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from backend.services.auth_service import get_current_user
from backend.services.job_service import get_job
from backend.models.database import PipelineEvent, PipelineRun

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

    run = None
    last_event = None
    try:
        run = (
            db.query(PipelineRun)
            .filter(PipelineRun.job_id == int(job_id))
            .order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc())
            .first()
        )
        if run is not None:
            last_event = (
                db.query(PipelineEvent)
                .filter(PipelineEvent.run_id == int(run.id))
                .order_by(PipelineEvent.created_at.desc(), PipelineEvent.id.desc())
                .first()
            )
    except ProgrammingError:
        # Local databases can be missing optional observability tables.
        # Keep the polling endpoint usable by returning the core job payload.
        db.rollback()
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
            "pipeline": (
                {
                    "run_id": int(run.id),
                    "pipeline_type": run.pipeline_type,
                    "status": run.status,
                    "request_id": run.request_id,
                    "upload_id": run.upload_id,
                    "normalization_run_id": run.normalization_run_id,
                    "detection_run_id": run.detection_run_id,
                    "warning_count": int(run.warning_count or 0),
                    "error_count": int(run.error_count or 0),
                    "last_stage": getattr(last_event, "stage", None),
                    "last_event_type": getattr(last_event, "event_type", None),
                    "last_message": getattr(last_event, "message", None),
                    "last_event_at": last_event.created_at.isoformat()
                    if getattr(last_event, "created_at", None)
                    else None,
                }
                if run is not None
                else None
            ),
        },
    }
