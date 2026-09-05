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
    moved here when a since-removed /jobs/skill-gap endpoint needed the
    same lookup, and kept here because it's fundamentally a JobPosting
    query, not roadmap-specific. api/routes/roadmaps.py is its only caller
    now; api/routes/jobs.py uses the aggregation helpers below.

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

    Each returned dict also carries `postings_requiring_count`: how many
    of the given `job_postings` have a job_posting_skill row for that
    skill (scoped to this call's postings only, not every posting in the
    DB that happens to need the skill). New/additive field -- existing
    consumers that only read the other keys (api/routes/jobs.py's
    /jobs/match skill-gap) are unaffected.
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
            job_posting_skill.c.job_posting_id,
        )
        .select_from(job_posting_skill)
        .join(Skill, Skill.id == job_posting_skill.c.skill_id)
        .where(job_posting_skill.c.job_posting_id.in_(posting_ids))
    ).all()

    aggregated: dict[uuid.UUID, dict] = {}
    # job_posting_skill's primary key is (job_posting_id, skill_id), so at
    # most one row per pair -- this set's size is exactly the count of
    # distinct postings-in-scope that needed the skill.
    posting_ids_by_skill: dict[uuid.UUID, set[uuid.UUID]] = {}
    for skill_id, name, category, requirement_level, job_posting_id in rows:
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
        posting_ids_by_skill.setdefault(skill_id, set()).add(job_posting_id)

    for skill_id, entry in aggregated.items():
        entry["postings_requiring_count"] = len(posting_ids_by_skill[skill_id])

    return list(aggregated.values())


def get_user_skill_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(select(user_skill.c.skill_id).where(user_skill.c.user_id == user_id))
    )


def get_user_skill_proficiency(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """skill_id -> proficiency_level (0-100) for this user's skills, from
    user_skill.proficiency_level (populated by resume extraction --
    services/skill_extraction.py / api/routes/resumes.py). Used by
    api/routes/roadmaps.py to ground a roadmap's current_level numbers in
    a real estimate instead of an LLM guess. A skill with no estimate
    (NULL -- e.g. an older row) is omitted; callers default a missing key
    to 0, same as a skill the user doesn't have at all.
    """
    rows = db.execute(
        select(user_skill.c.skill_id, user_skill.c.proficiency_level).where(
            user_skill.c.user_id == user_id,
            user_skill.c.proficiency_level.is_not(None),
        )
    ).all()
    return {skill_id: level for skill_id, level in rows}
