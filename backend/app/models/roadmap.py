

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

    # {"<step_order>": [<action_item index>, ...]} -- which action_items the
    # user has checked off per step. Null for rows predating this column
    # and for rows where nothing's been checked yet; api/routes/roadmaps.py
    # coerces null to {} at read time. Written via
    # repositories/roadmaps.py's set_action_item_done, never by AI generation.
    completed_action_items: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source_postings = relationship("JobPosting", secondary=roadmap_job_posting)
