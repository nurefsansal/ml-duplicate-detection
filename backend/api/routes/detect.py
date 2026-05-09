import io
import os
import multiprocessing
from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from backend.schemas.requests import DetectRequest
from backend.schemas.responses import DetectResponse
from backend.services.detection_service import detect_core, detect_file_dataframe
from backend.services.job_service import create_job, update_job_progress
from backend.services.pipeline_log_service import (
    add_pipeline_event,
    create_pipeline_run,
    finalize_pipeline_run,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

router = APIRouter()


def _run_detection_job(
    *,
    payload: DetectRequest,
    job_id: int | None,
    request_id: str | None,
):
    db = SessionLocal()
    run_log_id: int | None = None
    try:
        run_log = create_pipeline_run(
            db,
            pipeline_type="detection",
            request_id=request_id,
            upload_id=payload.uploadId,
            job_id=job_id,
            normalization_run_id=payload.normalizationRunId,
            metadata={"minRulesToMatch": payload.minRulesToMatch},
        )
        run_log_id = run_log.id
        add_pipeline_event(
            db,
            run_id=run_log.id,
            stage="detect",
            event_type="started",
            message="Mükerrer tespit başladı",
        )
        db.commit()

        detect_core(
            records=payload.records,
            min_rules_to_match=payload.minRulesToMatch,
            save_to_db=payload.saveToDb,
            session_id=payload.sessionId,
            upload_id=payload.uploadId,
            normalization_run_id=payload.normalizationRunId,
            job_id=job_id,
            background_mode=True,
        )

        if run_log_id is not None:
            add_pipeline_event(
                db,
                run_id=run_log_id,
                stage="detect",
                event_type="completed",
                message="Mükerrer tespit tamamlandı",
            )
            finalize_pipeline_run(db, run_id=run_log_id, status="completed")
        if job_id is not None:
            update_job_progress(db, job_id=job_id, status="completed", progress=100.0)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if job_id is not None:
            update_job_progress(db, job_id=job_id, status="failed", error_message=str(exc))
        if run_log_id is not None:
            add_pipeline_event(
                db,
                run_id=run_log_id,
                stage="detect",
                event_type="failed",
                message=str(exc),
            )
            finalize_pipeline_run(db, run_id=run_log_id, status="failed", error_message=str(exc))
        db.commit()
    finally:
        db.close()


def _run_detection_job_process(payload_dict: dict[str, Any], job_id: int | None, request_id: str | None) -> None:
    # Windows uses spawn; keep target top-level and arguments pickle-friendly.
    payload = DetectRequest(**payload_dict)
    _run_detection_job(payload=payload, job_id=job_id, request_id=request_id)


@router.post("/detect", response_model=DetectResponse)
def detect(background_tasks: BackgroundTasks, request: Request, payload: DetectRequest):
    db = SessionLocal()
    job = create_job(db, job_type="detection")
    if job is not None:
        db.commit()
    try:
        # P0: Always run detection async when using DB scope (uploadId/normalizationRunId).
        # This prevents request timeouts and avoids blocking the web worker.
        if payload.uploadId is not None or payload.normalizationRunId is not None:
            req_id = getattr(getattr(request, "state", None), "request_id", None)
            if job is not None:
                update_job_progress(
                    db,
                    job_id=job.id,
                    status="running",
                    progress=1.0,
                    total_rows=0,
                    processed_rows=0,
                    error_message="",
                )
                db.commit()

            p = multiprocessing.Process(
                target=_run_detection_job_process,
                args=(payload.model_dump(), job.id if job is not None else None, req_id),
                daemon=True,
            )
            p.start()

            return {
                "sessionId": payload.sessionId or "",
                "jobId": job.id if job is not None else None,
                "uploadId": payload.uploadId,
                "normalizationRunId": payload.normalizationRunId,
                "detectionRunId": None,
                "candidatePairs": 0,
                "candidatePairsLimited": False,
                "duplicatePairs": 0,
                "duplicateGroupCount": 0,
                "affectedRecordCount": 0,
                "insertedRows": 0,
                "totalRecords": None,
                "duplicates": [],
            }

        try:
            return detect_core(
                records=payload.records,
                min_rules_to_match=payload.minRulesToMatch,
                save_to_db=payload.saveToDb,
                session_id=payload.sessionId,
                upload_id=payload.uploadId,
                normalization_run_id=payload.normalizationRunId,
                job_id=job.id if job is not None else None,
                background_mode=False,
            )
        except HTTPException as exc:
            if exc.status_code != 413:
                raise

            req_id = getattr(getattr(request, "state", None), "request_id", None)
            if job is not None:
                # Clear any stale error message if detect_core raised 413.
                update_job_progress(
                    db,
                    job_id=job.id,
                    status="running",
                    progress=1.0,
                    error_message="",
                )
                db.commit()
            # BackgroundTasks runs in the same server process and can block request handling
            # for CPU-heavy detection. Run detection in a separate process instead.
            p = multiprocessing.Process(
                target=_run_detection_job_process,
                args=(payload.model_dump(), job.id if job is not None else None, req_id),
                daemon=True,
            )
            p.start()

            return {
                "sessionId": payload.sessionId or "",
                "jobId": job.id if job is not None else None,
                "uploadId": payload.uploadId,
                "normalizationRunId": payload.normalizationRunId,
                "detectionRunId": None,
                "candidatePairs": 0,
                "candidatePairsLimited": False,
                "duplicatePairs": 0,
                "duplicateGroupCount": 0,
                "affectedRecordCount": 0,
                "insertedRows": 0,
                "totalRecords": None,
                "duplicates": [],
            }
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
