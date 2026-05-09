from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.database import PipelineEvent, PipelineRun


def create_pipeline_run(
    session: Session,
    *,
    pipeline_type: str,
    status: str = "running",
    request_id: str | None = None,
    upload_id: int | None = None,
    job_id: int | None = None,
    normalization_run_id: int | None = None,
    detection_run_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> PipelineRun:
    run = PipelineRun(
        pipeline_type=pipeline_type,
        status=status,
        request_id=request_id,
        upload_id=upload_id,
        job_id=job_id,
        normalization_run_id=normalization_run_id,
        detection_run_id=detection_run_id,
        meta=metadata or {},
        created_at=datetime.utcnow(),
        started_at=datetime.utcnow() if status == "running" else None,
    )
    session.add(run)
    session.flush()
    return run


def add_pipeline_event(
    session: Session,
    *,
    run_id: int,
    stage: str,
    event_type: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    total_rows: int | None = None,
    processed_rows: int | None = None,
    warning_count: int | None = None,
    error_count: int | None = None,
    duration_ms: int | None = None,
) -> PipelineEvent:
    event = PipelineEvent(
        run_id=int(run_id),
        stage=stage,
        event_type=event_type,
        message=message,
        payload=payload or {},
        total_rows=int(total_rows or 0),
        processed_rows=int(processed_rows or 0),
        warning_count=int(warning_count or 0),
        error_count=int(error_count or 0),
        duration_ms=duration_ms,
        created_at=datetime.utcnow(),
    )
    session.add(event)
    session.flush()
    return event


def finalize_pipeline_run(
    session: Session,
    *,
    run_id: int,
    status: str,
    total_rows: int | None = None,
    processed_rows: int | None = None,
    warning_count: int | None = None,
    error_count: int | None = None,
    error_message: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> PipelineRun | None:
    run = session.query(PipelineRun).filter(PipelineRun.id == int(run_id)).first()
    if run is None:
        return None

    run.status = status
    run.completed_at = datetime.utcnow()
    if run.started_at and run.completed_at:
        run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)

    if total_rows is not None:
        run.total_rows = int(total_rows)
    if processed_rows is not None:
        run.processed_rows = int(processed_rows)
    if warning_count is not None:
        run.warning_count = int(warning_count)
    if error_count is not None:
        run.error_count = int(error_count)
    if error_message is not None:
        run.error_message = error_message

    if metadata_patch:
        merged = dict(run.meta or {})
        merged.update(metadata_patch)
        run.meta = merged

    session.flush()
    return run

