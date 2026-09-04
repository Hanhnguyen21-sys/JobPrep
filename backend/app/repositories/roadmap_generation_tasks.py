"""Repository for RoadmapGenerationTask -- create + status transitions,
shared by api/routes/roadmaps.py (enqueue + status endpoint) and its
background task runner (_run_roadmap_generation_task).

Unlike repositories/job_search_tasks.py, no enqueue-dedup here: a roadmap
generation is per-user/per-selection, not a shared cache_key, so every
POST /roadmaps creates its own task row and there's nothing to dedupe
concurrent requests against.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.roadmap_generation_task import RoadmapGenerationTask


def create_task(
    db: Session, *, user_id: uuid.UUID, job_posting_ids: list[uuid.UUID]
) -> RoadmapGenerationTask:
    """Flushes (assigns `task.id`) but does not commit -- caller controls
    the transaction boundary, same convention as repositories/roadmaps.py.
    """
    task = RoadmapGenerationTask(
        user_id=user_id, job_posting_ids=job_posting_ids, status="queued"
    )
    db.add(task)
    db.flush()
    return task


def get_task(
    db: Session, task_id: uuid.UUID, user_id: uuid.UUID
) -> RoadmapGenerationTask | None:
    """Scoped to `user_id` -- unlike JobSearchTask (shared/global
    ingestion data), a roadmap generation is private to whoever requested
    it, so a task_id belonging to another user must read back as "not
    found," not leak that user's generation status.
    """
    return db.scalar(
        select(RoadmapGenerationTask).where(
            RoadmapGenerationTask.id == task_id,
            RoadmapGenerationTask.user_id == user_id,
        )
    )


def mark_running(db: Session, task: RoadmapGenerationTask) -> None:
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)


def mark_finished(
    db: Session,
    task: RoadmapGenerationTask,
    *,
    status: str,
    roadmap_id: uuid.UUID | None = None,
    error_summary: str | None = None,
) -> None:
    """`status` is 'completed' or 'failed'."""
    task.status = status
    task.completed_at = datetime.now(timezone.utc)
    task.roadmap_id = roadmap_id
    task.error_summary = error_summary
