"""Roadmap -- one row per generated learning roadmap.

Built from a snapshot of up to MAX_SELECTED_POSTINGS (10, see
schemas/roadmap.py) job postings the user checked on /jobs (User_Job_Selection
-- see api/routes/roadmaps.py, services/roadmap.py). The Roadmap_Job_posting
join table lives in this file, same convention as Job_posting_Skill living
in models/job_posting.py -- it just records which postings a given roadmap
was generated from, no extra columns, unlike job_posting_skill/user_skill,
since there's nothing per-pair to describe beyond membership.

`steps` (and now `overview`) are stored as JSONB rather than normalized
tables -- a roadmap's step list and overview are only ever read/written as
a whole alongside the rest of that one roadmap, never queried or joined
against independently, so a separate table would add join complexity
nothing here needs. This is the DB-persisted version of the same "AI
result as one shaped object" idea schemas/roadmap.py and services/roadmap.py
already use in memory.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# Roadmap <-> JobPosting (many-to-many). Records which postings a roadmap
# was generated from -- no extra columns, unlike job_posting_skill/
# user_skill, since there's nothing per-pair to describe beyond membership.
roadmap_job_posting = Table(
    "roadmap_job_posting",
    Base.metadata,
    Column(
        "roadmap_id",
        UUID(as_uuid=True),
        ForeignKey("roadmaps.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "job_posting_id",
        UUID(as_uuid=True),
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

   
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

  
    target_position: Mapped[str] = mapped_column(Text, nullable=False)

  
    summary: Mapped[str] = mapped_column(Text, nullable=False)

   
    overview: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source_postings = relationship("JobPosting", secondary=roadmap_job_posting)
