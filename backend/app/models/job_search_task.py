"""JobSearchTask -- tracks one background refresh of a normalized
job-search query (ingestion/query_normalization.cache_key), so
POST /jobs/match can enqueue a refresh and return immediately instead of
blocking on the live ATS+OpenAI pipeline (see api/routes/jobs.py, Phase 3
of the /jobs/match latency work).

Durability note: the *execution* of a queued task currently runs via
FastAPI's BackgroundTasks (see api/routes/jobs.py's _run_refresh_task),
not a separate durable worker process. BackgroundTasks runs in-process,
after the response is sent, on the same event loop as the web server --
if the server process crashes or restarts while a task is 'running', that
task is simply lost (stuck at 'running' forever, no automatic retry or
recovery). This table itself is durable (a real Postgres row survives a
restart), which is what a real queue (RQ/Celery+Redis, ARQ, etc.) would
read from if that infrastructure gets added later -- the schema here is
deliberately queue-agnostic for that reason. For a small app with
low-frequency ingestion, this tradeoff is acceptable; revisit if refresh
volume/reliability requirements grow.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class JobSearchTask(Base):
    __tablename__ = "job_search_task"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Same value as job_search_cache.target_position (see
    # query_normalization.cache_key) -- what this refresh is for.
    cache_key: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # 'queued' | 'running' | 'completed' | 'partial_failure' | 'failed'.
    # A partial unique index (db/sql/14_create_job_search_task.sql)
    # enforces at most one row with status in ('queued', 'running') per
    # cache_key at the database level -- that's what actually prevents
    # duplicate refresh jobs under a race between two requests, not
    # application code.
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sanitized (never the raw exception str -- see api/routes/jobs.py's
    # _run_refresh_task) summary for 'failed'/'partial_failure' rows.
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
