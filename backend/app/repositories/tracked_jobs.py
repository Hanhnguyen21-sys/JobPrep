"""TrackedJob repository -- persistence + lookup for the Tracker page,
shared by api/routes/tracker.py.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.job_posting import JobPosting
from app.models.tracked_job import TrackedJob


def get_or_create_tracked_job(
    db: Session, *, user_id: uuid.UUID, job_posting_id: uuid.UUID, status: str = "saved"
) -> tuple[TrackedJob, bool]:
    """Returns (tracked_job, created). If `user_id`/`job_posting_id`
    already has a row, returns it UNCHANGED -- re-selecting an
    already-tracked posting on Job Match (see
    frontend/src/hooks/useJobSelection.ts) must never reset an existing
    status (e.g. "applied") back to "saved". Relies on the database-level
    unique constraint (uq_tracked_jobs_user_job,
    db/sql/19_create_tracked_jobs.sql) to make concurrent selects
    race-safe: if two requests both try to insert at nearly the same
    instant, only one INSERT succeeds and the other hits IntegrityError
    here, which is caught by re-fetching rather than raising -- same
    pattern as repositories/job_search_tasks.py's enqueue_or_get_active.
    """
    existing = db.scalar(
        select(TrackedJob).where(
            TrackedJob.user_id == user_id,
            TrackedJob.job_posting_id == job_posting_id,
        )
    )
    if existing is not None:
        return existing, False

    tracked = TrackedJob(user_id=user_id, job_posting_id=job_posting_id, status=status)
    db.add(tracked)
    try:
        db.flush()
        return tracked, True
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(TrackedJob).where(
                TrackedJob.user_id == user_id,
                TrackedJob.job_posting_id == job_posting_id,
            )
        )
        if existing is None:
            # Vanishingly unlikely (the row was deleted between our failed
            # insert and this re-fetch) -- fall back to a fresh attempt
            # rather than returning None to the caller.
            return get_or_create_tracked_job(
                db, user_id=user_id, job_posting_id=job_posting_id, status=status
            )
        return existing, False


def get_user_tracked_jobs(db: Session, user_id: uuid.UUID) -> list[TrackedJob]:
    return list(
        db.scalars(
            select(TrackedJob)
            .where(TrackedJob.user_id == user_id)
            .order_by(TrackedJob.created_at.desc())
            .options(selectinload(TrackedJob.job_posting).selectinload(JobPosting.company))
        )
    )


def get_tracked_job(
    db: Session, user_id: uuid.UUID, tracked_job_id: uuid.UUID
) -> TrackedJob | None:
    return db.scalar(
        select(TrackedJob)
        .where(TrackedJob.id == tracked_job_id, TrackedJob.user_id == user_id)
        .options(selectinload(TrackedJob.job_posting).selectinload(JobPosting.company))
    )


def update_tracked_job_status(db: Session, tracked_job: TrackedJob, status: str) -> TrackedJob:
    tracked_job.status = status
    db.flush()
    return tracked_job


def delete_tracked_job(db: Session, user_id: uuid.UUID, tracked_job_id: uuid.UUID) -> bool:
    """Delete a tracked_jobs row if it exists and belongs to user_id.
    Returns True if a row was deleted, False if no matching row was found
    (caller 404s in that case). Only ever deletes this user's tracking
    row -- the shared job_postings row it points at is never touched.
    Flushes but does not commit -- caller's transaction, same convention
    as repositories/roadmaps.py's delete_roadmap.
    """
    tracked = db.scalar(
        select(TrackedJob).where(
            TrackedJob.id == tracked_job_id, TrackedJob.user_id == user_id
        )
    )
    if tracked is None:
        return False
    db.delete(tracked)
    db.flush()
    return True
