"""Repository for JobSearchTask -- enqueue-with-dedup and status
transitions, shared by api/routes/jobs.py (enqueue + status endpoint) and
the background refresh runner (ingestion/runner.py's callers).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.job_search_task import JobSearchTask


def enqueue_or_get_active(db: Session, cache_key: str) -> tuple[JobSearchTask, bool]:
    """Returns (task, created). If a task for `cache_key` is already
    queued/running, returns that existing task with created=False instead
    of creating a duplicate -- relies on the database-level partial
    unique index (uq_job_search_task_active_per_key,
    db/sql/14_create_job_search_task.sql) to make this race-safe: if two
    requests both try to insert at nearly the same instant, only one
    INSERT succeeds and the other hits IntegrityError here, which we
    catch by re-fetching rather than raising.
    """
    task = JobSearchTask(cache_key=cache_key, status="queued")
    db.add(task)
    try:
        db.flush()
        return task, True
    except IntegrityError:
        db.rollback()
        existing = db.query(JobSearchTask).filter(
            JobSearchTask.cache_key == cache_key,
            JobSearchTask.status.in_(["queued", "running"]),
        ).order_by(JobSearchTask.created_at.desc()).first()
        if existing is None:
            # Vanishingly unlikely (the active task finished between our
            # failed insert and this re-fetch) -- fall back to a fresh
            # enqueue rather than returning None to the caller.
            return enqueue_or_get_active(db, cache_key)
        return existing, False


def get_task(db: Session, task_id: uuid.UUID) -> JobSearchTask | None:
    return db.get(JobSearchTask, task_id)


def mark_running(db: Session, task: JobSearchTask) -> None:
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)


def mark_finished(db: Session, task: JobSearchTask, *, status: str, error_summary: str | None = None) -> None:
    """`status` is one of 'completed' | 'partial_failure' | 'failed'."""
    task.status = status
    task.completed_at = datetime.now(timezone.utc)
    task.error_summary = error_summary


def delete_old_finished_tasks(db: Session, older_than: timedelta) -> int:
    """Retention helper: removes finished (completed/partial_failure/
    failed) task rows older than `older_than`. Not currently wired to run
    automatically -- there's no scheduler/cron infrastructure in this
    project (see the broader ingestion redesign notes) -- so call this
    from a one-off script or wire it into one if/when that exists. Never
    deletes 'queued'/'running' rows regardless of age, since an
    in-progress task being deleted out from under _run_refresh_task would
    orphan it.
    """
    cutoff = datetime.now(timezone.utc) - older_than
    result = db.execute(
        delete(JobSearchTask).where(
            JobSearchTask.status.in_(["completed", "partial_failure", "failed"]),
            JobSearchTask.completed_at < cutoff,
        )
    )
    return result.rowcount
