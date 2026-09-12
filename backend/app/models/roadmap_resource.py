"""RoadmapResource -- a directory catalog, one row per top-level
roadmap in the developer-roadmap GitHub project
(https://github.com/nilbuild/developer-roadmap/tree/master/roadmaps),
e.g. slug="machine-learning" -> the GitHub tree URL for
roadmaps/machine-learning.

Deliberately NOT one row per article/video/course link inside those
roadmaps (that per-topic-resource shape -- migration 17's original
intent -- was replaced by migration 18 after review; those ~23k rows are
preserved under `roadmap_resources_topic_backup`, not deleted). This
table is the one services/roadmap_resources.py reads from at
roadmap-generation time to attach a "here's the full learning roadmap for
this skill" link -- see that module for the skill-name -> slug matching
(aliases + direct slugify) that decides which row (if any) applies to a
given skill.

Populated by scripts/import_roadmap_resources.py, never at request time,
and never by calling GitHub during roadmap generation itself -- that
script is the only writer.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class RoadmapResource(Base):
    __tablename__ = "roadmap_resources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Top-level roadmaps/<slug> directory name from the developer-roadmap
    # repo (e.g. "machine-learning", "python") -- one row per slug.
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)  # display name, derived from slug
    url: Mapped[str] = mapped_column(Text, nullable=False)  # GitHub directory URL (contents API's html_url)

    # False once a sync no longer sees this slug in the source repo's
    # roadmaps/ directory -- never deleted, so a link already attached to
    # an existing saved roadmap keeps resolving even if the upstream
    # roadmap is later renamed/removed. Only services/roadmap_resources.py's
    # *new*-roadmap matching filters on this; old saved roadmaps' stored
    # resource dicts are unaffected either way (see models/roadmap.py).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
