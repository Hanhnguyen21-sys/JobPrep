"""Roadmap routes.

POST /roadmaps is the User_Job_Selection -> roadmap step: the frontend
sends the job postings the user checked on /jobs (capped at
MAX_SELECTED_POSTINGS, see schemas/job.py), this route resolves them,
combines their descriptions into a single prompt, and asks
services/roadmap.py for one roadmap that covers all of them together --
not the individual per-posting skill_gap api/routes/jobs.py's
/jobs/skill-gap (the fast, free, unpersisted "quick prep note" alternative
to this) returns. Unlike /jobs/match's or /jobs/skill-gap's responses,
the result here is persisted (`Roadmap` + `roadmap_job_posting`), since a
roadmap is meant to be revisited later, not just a one-off check --
hence also the GET routes below, the auto-generated `title` (see
_build_title) that makes those persisted roadmaps distinguishable in a
history list, and DELETE for removing ones the user no longer wants
cluttering that history.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.db.session import get_db
from app.models.job_posting import JobPosting
from app.models.roadmap import Roadmap
from app.models.skill import Skill
from app.models.user import User, user_skill
from app.repositories.jobs import get_job_postings_by_ids
from app.repositories.roadmaps import (
    create_roadmap,
    delete_roadmap,
    get_roadmap,
    get_user_roadmaps,
)
from app.schemas.roadmap import (
    RoadmapCreateRequest,
    RoadmapOverview,
    RoadmapResponse,
    RoadmapSourcePosting,
    RoadmapStep,
)
from app.services.roadmap import generate_roadmap

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _build_title(job_postings: list[JobPosting], now: datetime) -> str:
    """Deterministic label distinguishing this roadmap from others in the
    user's /roadmaps history -- e.g. "Coinbase & 1 more (3 postings) --
    Aug 15". Built from the selected postings' companies, count, and
    today's date, not from anything the AI returns -- keeps it stable and
    free (no extra token spend/round-trip just to name the thing).
    """
    companies = list(dict.fromkeys(jp.company.name for jp in job_postings))
    if len(companies) == 1:
        company_part = companies[0]
    elif len(companies) == 2:
        company_part = f"{companies[0]} & {companies[1]}"
    else:
        company_part = f"{companies[0]} & {len(companies) - 1} more"

    count = len(job_postings)
    posting_word = "posting" if count == 1 else "postings"
    return f"{company_part} ({count} {posting_word}) — {now:%b %d}"


def _legacy_overview(roadmap: Roadmap) -> dict:
    """Roadmaps created before migration 10 have `overview = null` and
    only the old flat `summary` text. Backfills a RoadmapOverview shape
    from that at read time so old roadmaps still load instead of failing
    RoadmapResponse validation -- best-effort, not a real backfill:
    `priority_skills`/`estimated_duration` have no old data to source from,
    so they come back empty.
    """
    if roadmap.overview:
        return roadmap.overview
    return {
        "headline": roadmap.summary,
        "priority_skills": [],
        "estimated_duration": "",
    }


def _legacy_step(step: dict) -> dict:
    """Roadmaps created before this schema change stored steps shaped like
    {order, title, description, skills_to_develop}. Adapts those into the
    new RoadmapStep shape so old roadmaps still load -- best-effort:
    `why_it_matters` carries the old description forward, `focus_skill`
    takes the first old skill (if any), and action_items/resources/
    success_criteria come back empty since there's no old data to source
    them from.
    """
    if "why_it_matters" in step:
        return step  # already new-shape

    skills = step.get("skills_to_develop", [])
    return {
        "order": step["order"],
        "title": step["title"],
        "focus_skill": skills[0] if skills else "",
        "skills": skills,
        "why_it_matters": step.get("description", ""),
        "action_items": [],
        "resources": [],
        "project": None,
        "duration": "",
        "success_criteria": [],
    }


def _to_response(roadmap: Roadmap) -> RoadmapResponse:
    return RoadmapResponse(
        id=roadmap.id,
        title=roadmap.title,
        target_position=roadmap.target_position,
        overview=RoadmapOverview(**_legacy_overview(roadmap)),
        steps=[RoadmapStep(**_legacy_step(step)) for step in roadmap.steps],
        source_postings=[
            RoadmapSourcePosting(id=jp.id, company_name=jp.company.name, title=jp.title)
            for jp in roadmap.source_postings
        ],
        created_at=roadmap.created_at,
    )


@router.post("", response_model=RoadmapResponse)
def create_roadmap_from_selection(
    payload: RoadmapCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapResponse:
    if not current_user.target_position:
        raise BadRequestException(
            "No target position set -- submit a resume with a target position first."
        )

    # De-dup up front -- Field(max_length=...) on the request schema counts
    # raw list entries, so a request repeating one id past the cap could
    # otherwise slip through with fewer *distinct* postings than the limit
    # implies. Order preserved (dict.fromkeys, not set()) purely so error
    # messages / prompts stay in the order the user picked them.
    requested_ids = list(dict.fromkeys(payload.job_posting_ids))

    job_postings = get_job_postings_by_ids(db, requested_ids)
    found_ids = {jp.id for jp in job_postings}
    missing_ids = [jp_id for jp_id in requested_ids if jp_id not in found_ids]
    if missing_ids:
        raise BadRequestException(
            f"{len(missing_ids)} selected posting(s) could not be found -- "
            "they may have been removed. Refresh your matches and try again."
        )

    existing_skill_names = list(
        db.scalars(
            select(Skill.name)
            .select_from(user_skill)
            .join(Skill, Skill.id == user_skill.c.skill_id)
            .where(user_skill.c.user_id == current_user.id)
        )
    )

    result = generate_roadmap(
        target_position=current_user.target_position,
        existing_skills=existing_skill_names,
        postings=[
            {
                "company_name": jp.company.name,
                "title": jp.title,
                "description": jp.description,
            }
            for jp in job_postings
        ],
    )

    if result is None:
        raise BadRequestException(
            "Couldn't generate a roadmap from these postings -- try again, "
            "or try a different selection."
        )

    roadmap = create_roadmap(
        db,
        user_id=current_user.id,
        title=_build_title(job_postings, datetime.now(timezone.utc)),
        target_position=current_user.target_position,
        # `summary` kept in sync with `overview.headline` for now rather
        # than left blank -- it's a deprecated column (see models/roadmap.py)
        # but not dropped, so it stays a sane one-line summary instead of
        # going stale/empty on every new row.
        summary=result.overview.headline,
        overview=result.overview.model_dump(),
        steps=[step.model_dump() for step in result.steps],
        job_postings=job_postings,
    )
    db.commit()
    db.refresh(roadmap)

    return _to_response(roadmap)


@router.get("", response_model=list[RoadmapResponse])
def list_roadmaps(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RoadmapResponse]:
    return [_to_response(r) for r in get_user_roadmaps(db, current_user.id)]


@router.get("/{roadmap_id}", response_model=RoadmapResponse)
def get_roadmap_detail(
    roadmap_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapResponse:
    roadmap = get_roadmap(db, current_user.id, roadmap_id)
    if roadmap is None:
        raise NotFoundException("Roadmap not found")
    return _to_response(roadmap)


@router.delete("/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_roadmap_route(
    roadmap_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    deleted = delete_roadmap(db, current_user.id, roadmap_id)
    if not deleted:
        raise NotFoundException("Roadmap not found")
    db.commit()
