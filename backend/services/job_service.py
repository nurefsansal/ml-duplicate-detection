from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.models.database import Job


def create_job(session: Session, *, job_type: str, status: str = "running") -> Job | None:
    job = Job(type=job_type, status=status, progress=0.0, total_rows=0, processed_rows=0)
    try:
        session.add(job)
        session.flush()
        return job
    except ProgrammingError:
        session.rollback()
        return None


def update_job_progress(
    session: Session,
    *,
    job_id: int,
    status: str | None = None,
    progress: float | None = None,
    total_rows: int | None = None,
    processed_rows: int | None = None,
    error_message: str | None = None,
) -> Job | None:
    if job_id is None:
        return None
    job = session.query(Job).filter(Job.id == int(job_id)).first()
    if job is None:
        return None
    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = max(0.0, min(100.0, float(progress)))
    if total_rows is not None:
        job.total_rows = int(total_rows)
    if processed_rows is not None:
        job.processed_rows = int(processed_rows)
    if error_message is not None:
        job.error_message = error_message
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()
    return job


def get_job(session: Session, *, job_id: int) -> Job | None:
    try:
        return session.query(Job).filter(Job.id == int(job_id)).first()
    except ProgrammingError:
        session.rollback()
        return None
