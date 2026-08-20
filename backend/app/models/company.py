"""Company — one row per company we pull jobs from.

Ingestion path 1 (Greenhouse/Lever APIs, see app/ingestion/) upserts these
rows keyed on (ats_platform, ats_identifier) — see the unique constraint in
db/sql/4_create_companies_and_job_postings.sql. A usable company needs
*one* of (ats_platform + ats_identifier) or career_page_url; that's
enforced at the ingestion layer, not the schema, same as how Skill.category
validity is enforced at the Pydantic layer rather than a DB enum.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    # 'greenhouse' | 'lever' -- which ingestion/*.py client ats_identifier
    # resolves against. Nullable because a company added via a future
    # career-page path wouldn't have one.
    ats_platform: Mapped[str | None] = mapped_column(String, nullable=True)
    ats_identifier: Mapped[str | None] = mapped_column(String, nullable=True)

    career_page_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job_postings = relationship("JobPosting", back_populates="company")
