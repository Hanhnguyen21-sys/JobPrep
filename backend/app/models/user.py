"""User table.

Important: this is a `public.users` PROFILE table, not Supabase's own
`auth.users` table (which we don't manage — Supabase Auth owns it). This
row's primary key is the *same UUID* as the matching `auth.users.id`, so it
can be created either by:

  1. A Postgres trigger on `auth.users` (see
     backend/app/db/sql/1_create_users_and_trigger.sql) that inserts a
     row here whenever someone signs up, or
  2. The `/auth/sync` endpoint the first time an authenticated request
     comes in, as a fallback.

The User_Skill join table (many-to-many) lives in this file per the
file-structure plan.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# User <-> Skill (many-to-many). confidence/evidence/source are populated
# by resume skill extraction (services/skill_extraction.py) and describe
# *this user's* link to *this skill* — not a property of the skill itself,
# which is why they live here rather than on Skill. All three are nullable
# because a skill could theoretically get linked another way later (e.g.
# the user manually adding one) without that context existing.
#
# `origin` records *how* this link was created ("resume" for now — the
# only pathway that exists yet). This is what lets resume resubmission
# safely delete rows that fell off the new resume without also deleting
# rows created some other way in the future (e.g. a manual "add a skill"
# feature) — the sync only ever touches rows matching its own origin.
user_skill = Table(
    "user_skill",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    Column("confidence", String, nullable=True),
    Column("evidence", Text, nullable=True),
    Column("source", String, nullable=True),
    Column("origin", String, nullable=False, server_default="resume"),
)


class User(Base):
    __tablename__ = "users"

    # Same UUID as the corresponding auth.users row.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # The job title/role the user is looking for, captured alongside their
    # resume submission (see api/routes/resumes.py). Persisted -- unlike
    # resume text itself, which is discarded after extraction -- because
    # api/routes/jobs.py's targeted-ingestion endpoint reads it on every
    # "Find Matching Jobs" call, not just the one that first set it.
    target_position: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skills = relationship("Skill", secondary=user_skill, backref="users")
