"""RoadmapGenerationTask -- tracks one background POST /roadmaps
generation (fetch descriptions + extract skills for whichever selected
postings need it, then generate + persist the roadmap itself), so the
request can return immediately instead of blocking on up to
MAX_SELECTED_POSTINGS sequential description fetches plus two LLM calls.
Same in-process FastAPI BackgroundTasks pattern and durability caveat as
models/job_search_task.py -- see that module's docstring for the caveat
in full (not repeated here).

Unlike JobSearchTask, not deduped/shared across requests: a roadmap
generation is inherently per-user and per-selection (existing skills,
target position, and the exact set of selected postings all vary), so
there's no shared cache_key to dedupe concurrent requests against -- every
POST /roadmaps creates its own task row, and a task's status is only ever
visible to the user who created it (see api/routes/roadmaps.py's status
endpoint, which scopes the lookup by user_id -- unlike JobSearchTask,
which is intentionally not user-scoped).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class RoadmapGenerationTask(Base):
    __tablename__ = "roadmap_generation_task"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Snapshot of the requested job_posting_ids -- the background task
    # runner opens its own DB session (see api/routes/roadmaps.py's
    # _run_roadmap_generation_task) and re-resolves these itself rather
    # than receiving live ORM objects from the request's session.
    job_posting_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )

    # 'queued' | 'running' | 'completed' | 'failed'.
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")

    # Set once status='completed'. The status endpoint returns this
    # pointer rather than the full RoadmapResponse itself -- the frontend
    # re-fetches via GET /roadmaps/{roadmap_id} once terminal, same split
    # api/routes/jobs.py's GET /jobs/match/status uses (status + pointer,
    # not the payload).
    roadmap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sanitized -- never a raw exception str, same convention as
    # JobSearchTask.error_summary (see api/routes/jobs.py's
    # _run_refresh_task for why).
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
