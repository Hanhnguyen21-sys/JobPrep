"""Skill repository -- shared case-insensitive get-or-create for `Skill`
rows. Used by api/routes/resumes.py (resume skill extraction) and
ingestion/runner.py (job posting skill extraction), so there's exactly one
place this lookup lives instead of two copies that could drift.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.skill import Skill


def get_or_create_skill(db: Session, name: str, category: str) -> Skill:
    """Case-insensitive get-or-create.

    Known simplification: there's a small race window between this SELECT
    and the INSERT below if two requests/runs extract the same brand-new
    skill at the same instant. Not worth guarding against yet at MVP
    scale -- would need a DB-level `ON CONFLICT (lower(name))` unique
    index to close properly.
    """
    existing = db.scalar(
        select(Skill).where(func.lower(Skill.name) == name.strip().lower())
    )
    if existing is not None:
        return existing

    skill = Skill(name=name.strip(), category=category)
    db.add(skill)
    db.flush()  # assigns skill.id (client-side uuid default) without committing yet
    return skill
