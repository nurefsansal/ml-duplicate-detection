import io
import os

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.schemas.requests import DetectRequest
from backend.schemas.responses import DetectResponse
from backend.services.detection_service import detect_core, detect_file_dataframe
from backend.services.job_service import create_job, update_job_progress

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

router = APIRouter()


@router.post("/detect", response_model=DetectResponse)
def detect(payload: DetectRequest):
    db = SessionLocal()
    job = create_job(db, job_type="detection")
    if job is not None:
        db.commit()
    try:
        result = detect_core(
            records=payload.records,
            min_rules_to_match=payload.minRulesToMatch,
            save_to_db=payload.saveToDb,
            session_id=payload.sessionId,
            upload_id=payload.uploadId,
            normalization_run_id=payload.normalizationRunId,
            job_id=job.id if job is not None else None,
        )
        return result
    except Exception as exc:
        db.rollback()
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=str(exc),
            )
            db.commit()
        raise
    finally:
        db.close()


@router.post("/detect-file", response_model=DetectResponse)
async def detect_file(
    file: UploadFile = File(...),
    minRulesToMatch: int = Form(default=2),
    saveToDb: bool = Form(default=False),
    sessionId: str | None = Form(default=None),
    uploadId: int | None = Form(default=None),
):
    db = SessionLocal()
    job = create_job(db, job_type="detection")
    if job is not None:
        db.commit()
    try:
        filename = (file.filename or "").lower()
        content = await file.read()

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
            source_type = "csv"
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
            source_type = "excel"
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Use .xlsx, .xls or .csv",
            )

        if df.empty:
            raise HTTPException(status_code=400, detail="File has no usable rows")

        result = detect_file_dataframe(
            df_original=df,
            file_name=file.filename or "uploaded_file",
            source_type=source_type,
            min_rules_to_match=minRulesToMatch,
            save_to_db=saveToDb,
            session_id=sessionId,
            upload_id=uploadId,
            job_id=job.id if job is not None else None,
        )
        return result
    except Exception as exc:
        db.rollback()
        if job is not None:
            update_job_progress(
                db,
                job_id=job.id,
                status="failed",
                error_message=str(exc),
            )
            db.commit()
        raise
    finally:
        db.close()
