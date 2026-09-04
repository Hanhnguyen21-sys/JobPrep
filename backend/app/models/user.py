

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


user_skill = Table(
    "user_skill",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
   
    Column("origin", String, nullable=False, server_default="resume"),
    Column("proficiency_level", Integer, nullable=True),
    Column("proficiency_confidence", String, nullable=True),
    CheckConstraint(
        "proficiency_level IS NULL OR proficiency_level BETWEEN 0 AND 100",
        name="ck_user_skill_proficiency_level_range",
    ),
    CheckConstraint(
        "proficiency_confidence IS NULL OR proficiency_confidence IN ('low', 'medium', 'high')",
        name="ck_user_skill_proficiency_confidence_values",
    ),
)


class User(Base):
    __tablename__ = "users"

    # Same UUID as the corresponding auth.users row.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)

   
    target_position: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skills = relationship("Skill", secondary=user_skill, backref="users")
