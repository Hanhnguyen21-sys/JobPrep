"""Skill — canonical and deduplicated across all users.

`category` ("technical" | "soft") is a property of the skill itself, not
of a particular user's resume — "Python" is always technical, regardless
of who has it. Per-user, per-extraction specifics (proficiency_level,
proficiency_confidence) live on the `user_skill` join table in
models/user.py instead, since those vary by user and by extraction, not
by skill.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # "technical" | "soft". Kept as a plain string rather than a Postgres
    # enum type so adding a third category later doesn't require an enum
    # migration — validity is enforced at the Pydantic layer instead
    # (see schemas/resume.py).
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
