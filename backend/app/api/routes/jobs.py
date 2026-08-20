"""Job routes.

POST /jobs/match runs ingestion path 1 (Greenhouse/Lever) scoped and
filtered to the current user's target_position (models/user.py,
api/routes/resumes.py) -- a fast, small pull, unlike the broad,
unfiltered pull ingestion/runner.py's standalone run_ingestion() does for
keeping job_postings generally populated. This is a distinct,
explicitly-triggered endpoint rather than bundled into resume submission:
fetch+filter+extract can take much longer than a typical request, so the
frontend calls this as its own step with its own loading state.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException
from app.db.session import get_db
from app.ingestion.runner import run_targeted_ingestion
from app.models.job_posting import JobPosting
from app.models.user import User
from app.repositories.jobs import aggregate_required_skills, get_user_skill_ids
from app.schemas.job import JobMatchResponse, MatchedJobPosting, SkillGapItem

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_matched_postings(job_postings: list[JobPosting]) -> list[MatchedJobPosting]:
    return [
        MatchedJobPosting(
            id=jp.id,
            company_name=jp.company.name,
            title=jp.title,
            location=jp.location,
            url=jp.url,
        )
        for jp in job_postings
    ]


def _to_skill_gap_items(
    skill_gap_raw: list[dict], have_ids: set[uuid.UUID]
) -> list[SkillGapItem]:
    return [
        SkillGapItem(
            skill_id=item["skill_id"],
            name=item["name"],
            category=item["category"],
            requirement_level=item["requirement_level"],
            user_has=item["skill_id"] in have_ids,
        )
        for item in skill_gap_raw
    ]


@router.post("/match", response_model=JobMatchResponse)
def find_matching_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobMatchResponse:
    if not current_user.target_position:
        raise BadRequestException(
            "No target position set -- submit a resume with a target position first."
        )

    job_postings = run_targeted_ingestion(db, current_user.target_position)

    skill_gap_raw = aggregate_required_skills(db, job_postings)
    have_ids = get_user_skill_ids(db, current_user.id)

    return JobMatchResponse(
        target_position=current_user.target_position,
        postings=_to_matched_postings(job_postings),
        skill_gap=_to_skill_gap_items(skill_gap_raw, have_ids),
    )
