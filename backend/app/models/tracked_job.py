"""TrackedJob -- one row per (user, job posting) the user has added to
their Tracker (app/api/routes/tracker.py). Created automatically the
first time a user selects a posting on Job Match (see
frontend/src/hooks/useJobSelection.ts), separate from JobPosting itself
so per-user application status never touches the shared/global posting
row, and separate from Roadmap's roadmap_job_posting -- a tracked job
has nothing to do with whether it fed a roadmap.

Deliberately NOT cleaned up when JobPosting.is_active flips to False
during ingestion (app/ingestion/runner.py never deletes JobPosting rows
either, for the same reason) -- a user's application history must
survive a posting going stale/removed from the board.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# Mirrors frontend/src/types/tracker.ts's TrackedJobStatus -- keep both in
# sync by hand, same convention as MAX_SELECTED_POSTINGS/job.ts.
TRACKED_JOB_STATUSES = (
    "saved",
    "applied",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
)


class TrackedJob(Base):
    __tablename__ = "tracked_jobs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "job_posting_id", name="uq_tracked_jobs_user_job"
        ),
        CheckConstraint(
            "status in ('saved','applied','interview','offer','rejected','withdrawn')",
            name="ck_tracked_jobs_status_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="saved"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Bumped on every status change via repositories/tracked_jobs.py's
    # update_tracked_job_status -- `onupdate` fires on any ORM-level UPDATE
    # of this row, not just status changes, but nothing else on this model
    # is ever mutated after creation.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job_posting = relationship("JobPosting")
