"""JobSearchCache — tracks the last time ingestion/runner.py's
run_targeted_ingestion() did a full live ATS pull for a given (normalized)
target position, so a repeat search within `freshness_minutes` can skip
straight to querying already-ingested `job_postings` instead of
re-hitting Greenhouse/Lever + re-running AI extraction. Shared across all
users -- a cache hit from one user's search benefits everyone searching
the same position, same reasoning as `job_postings`/`job_posting_skill`
themselves being global, not per-user.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class JobSearchCache(Base):
    __tablename__ = "job_search_cache"

    # Normalized (stripped + lowercased) target position -- the cache key.
    target_position: Mapped[str] = mapped_column(String, primary_key=True)
    last_ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
