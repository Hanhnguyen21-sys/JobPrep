"""Job posting repository -- read/aggregation helpers over JobPosting +
job_posting_skill, shared by api/routes/jobs.py and api/routes/roadmaps.py.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.job_posting import JobPosting, job_posting_skill
from app.models.skill import Skill
from app.models.user import user_skill


def get_job_postings_by_ids(
    db: Session, job_posting_ids: list[uuid.UUID]
) -> list[JobPosting]:
    """Fetch postings by id, eager-loading `company` -- every caller needs
    it (services/roadmap.py's AI prompt, and every response shape that
    reports company_name). Originally lived in repositories/roadmaps.py;
    moved here once api/routes/jobs.py's /jobs/skill-gap started needing
    the exact same lookup -- it's fundamentally a JobPosting query, not
    roadmap-specific.

    Order is NOT guaranteed to match `job_posting_ids`, and missing ids are
    silently omitted rather than raising -- callers that care about
    completeness (both api/routes/jobs.py and api/routes/roadmaps.py need
    to tell the user if a selected posting vanished) must check the
    returned set against what they asked for themselves.
    """
    if not job_posting_ids:
        return []

    return list(
        db.scalars(
            select(JobPosting)
            .where(JobPosting.id.in_(job_posting_ids))
            .options(selectinload(JobPosting.company))
        )
    )


def aggregate_required_skills(db: Session, job_postings: list[JobPosting]) -> list[dict]:
    """Union of skills required/preferred across `job_postings`. A skill
    required by *any* matched posting is reported as "required" even if
    another matched posting only listed it as preferred -- the stricter
    requirement should win, not get diluted by a looser one elsewhere.
    """
    if not job_postings:
        return []

    posting_ids = [jp.id for jp in job_postings]

    rows = db.execute(
        select(
            Skill.id,
            Skill.name,
            Skill.category,
            job_posting_skill.c.requirement_level,
        )
        .select_from(job_posting_skill)
        .join(Skill, Skill.id == job_posting_skill.c.skill_id)
        .where(job_posting_skill.c.job_posting_id.in_(posting_ids))
    ).all()

    aggregated: dict[uuid.UUID, dict] = {}
    for skill_id, name, category, requirement_level in rows:
        entry = aggregated.setdefault(
            skill_id,
            {
                "skill_id": skill_id,
                "name": name,
                "category": category,
                "requirement_level": "preferred",
            },
        )
        if requirement_level == "required":
            entry["requirement_level"] = "required"

    return list(aggregated.values())


def get_user_skill_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(select(user_skill.c.skill_id).where(user_skill.c.user_id == user_id))
    )
