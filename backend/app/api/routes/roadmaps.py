
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.db.session import SessionLocal, get_db
from app.models.job_posting import JobPosting
from app.models.roadmap import Roadmap
from app.models.skill import Skill
from app.models.user import User, user_skill
from app.repositories.jobs import get_job_postings_by_ids
from app.repositories.roadmap_generation_tasks import (
    create_task,
    get_task,
    mark_finished,
    mark_running,
)
from app.repositories.roadmaps import (
    create_roadmap,
    delete_roadmap,
    get_roadmap,
    get_user_roadmaps,
    set_action_item_done,
)
from app.ingestion.runner import hash_description, sync_job_posting_skills_batch
from app.services.job_description_fetch import fetch_job_description
from app.schemas.roadmap import (
    RoadmapCreateRequest,
    RoadmapGenerationAcceptedResponse,
    RoadmapGenerationStatusResponse,
    RoadmapOverview,
    RoadmapProgressResponse,
    RoadmapProgressUpdate,
    RoadmapResponse,
    RoadmapSourcePosting,
    RoadmapStep,
)
from app.services.roadmap import generate_roadmap

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _build_title(job_postings: list[JobPosting], now: datetime) -> str:
    
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

def _ensure_descriptions(db: Session, job_postings: list[JobPosting]) -> None:
    """Fetches + extracts skills for any selected posting
    that's missing a description, or whose fetched content has changed
    since it was last extracted (see hash_description/
    sync_job_posting_skills_batch in ingestion/runner.py -- this is the
    selection-time wiring their module docstring says was still needed).

    """
    pending: list[tuple[JobPosting, str | None]] = []

    for jp in job_postings:
        if not jp.url:
            continue

        text = fetch_job_description(jp.url)
        if text is None:
            continue  # dead link/timeout/SPA/too-short -- leave as-is

        new_hash = hash_description(text)
        if new_hash == jp.description_hash:
            continue  # unchanged since last extraction -- skip re-billing the LLM

        jp.description = text
        pending.append((jp, new_hash))

    sync_job_posting_skills_batch(db, pending, log_prefix="[roadmaps]")
    if pending:
        db.commit()

def _legacy_priority_skill(skill: str | dict) -> dict:
   
    if isinstance(skill, str):
        return {"skill": skill, "current_level": 0, "target_level": 0}
    return skill


def _legacy_overview(roadmap: Roadmap) -> dict:
    
    if roadmap.overview:
        overview = dict(roadmap.overview)
        overview["priority_skills"] = [
            _legacy_priority_skill(skill)
            for skill in overview.get("priority_skills", [])
        ]
        return overview
    return {
        "headline": roadmap.summary,
        "priority_skills": [],
        "estimated_duration": "",
    }


def _legacy_step(step: dict) -> dict:
    
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
        completed_action_items=roadmap.completed_action_items or {},
        last_interacted_step_order=roadmap.last_interacted_step_order,
    )

def _run_roadmap_generation_task(
    task_id: uuid.UUID, user_id: uuid.UUID, job_posting_ids: list[uuid.UUID]
) -> None:
    """Runs via FastAPI BackgroundTasks, after the response for the
    POST /roadmaps request that enqueued it has already been sent. Opens
    its own DB session -- same pattern as api/routes/jobs.py's
    _run_refresh_task -- since it must outlive that request's
    session/lifecycle. Durability caveat: same as
    models/roadmap_generation_task.py's docstring (in-process
    BackgroundTasks, not a durable queue).

    Does the actual work POST /roadmaps used to do synchronously: fetch
    descriptions for whichever selected postings need it (up to
    MAX_SELECTED_POSTINGS sequential external fetches -- this is exactly
    why it's off the request path now), extract their skills, then
    generate + persist the roadmap.
    """
    db = SessionLocal()
    try:
        task = get_task(db, task_id, user_id)
        if task is None:
            return

        mark_running(db, task)
        db.commit()

        try:
            current_user = db.get(User, user_id)
            job_postings = get_job_postings_by_ids(db, job_posting_ids)

            _ensure_descriptions(db, job_postings)

            existing_skill_names = list(
                db.scalars(
                    select(Skill.name)
                    .select_from(user_skill)
                    .join(Skill, Skill.id == user_skill.c.skill_id)
                    .where(user_skill.c.user_id == user_id)
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
                mark_finished(
                    db,
                    task,
                    status="failed",
                    error_summary="Couldn't generate a roadmap from these postings.",
                )
                db.commit()
                return

            roadmap = create_roadmap(
                db,
                user_id=user_id,
                title=_build_title(job_postings, datetime.now(timezone.utc)),
                target_position=current_user.target_position,
                summary=result.overview.headline,
                overview=result.overview.model_dump(),
                steps=[step.model_dump() for step in result.steps],
                job_postings=job_postings,
            )
            mark_finished(db, task, status="completed", roadmap_id=roadmap.id)
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- genuinely unexpected (a bug or
            # DB/LLM error), not a per-posting failure (those are isolated
            # inside _ensure_descriptions/sync_job_posting_skills_batch
            # already). Never include str(exc) here -- only the
            # exception's type name, same reasoning as api/routes/jobs.py's
            # _run_refresh_task.
            db.rollback()
            mark_finished(
                db, task, status="failed", error_summary=f"{type(exc).__name__} during roadmap generation"
            )
            db.commit()
    finally:
        db.close()


@router.post("", response_model=RoadmapGenerationAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def create_roadmap_from_selection(
    payload: RoadmapCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapGenerationAcceptedResponse:
    """Validates the selection synchronously (cheap: a target_position
    check and one DB lookup), then enqueues the actual generation --
    description fetches + skill extraction + the two LLM calls -- as a
    background task and returns immediately. See
    _run_roadmap_generation_task for the work itself and
    GET /roadmaps/status/{task_id} for how the frontend polls it to
    completion (mirrors api/routes/jobs.py's POST /jobs/match ->
    GET /jobs/match/status split).
    """
    if not current_user.target_position:
        raise BadRequestException(
            "No target position set -- submit a resume with a target position first."
        )

    requested_ids = list(dict.fromkeys(payload.job_posting_ids))

    job_postings = get_job_postings_by_ids(db, requested_ids)
    found_ids = {jp.id for jp in job_postings}
    missing_ids = [jp_id for jp_id in requested_ids if jp_id not in found_ids]
    if missing_ids:
        raise BadRequestException(
            f"{len(missing_ids)} selected posting(s) could not be found -- "
            "they may have been removed. Refresh your matches and try again."
        )

    task = create_task(db, user_id=current_user.id, job_posting_ids=requested_ids)
    db.commit()

    background_tasks.add_task(
        _run_roadmap_generation_task, task.id, current_user.id, requested_ids
    )

    return RoadmapGenerationAcceptedResponse(task_id=task.id)


@router.get("/status/{task_id}", response_model=RoadmapGenerationStatusResponse)
def get_roadmap_generation_status(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapGenerationStatusResponse:
    """Polled by the frontend after POST /roadmaps' 202 response until
    `status` reaches a terminal state (completed/failed), then fetches
    GET /roadmaps/{roadmap_id} to load the full result. Scoped to
    current_user -- unlike api/routes/jobs.py's job-search tasks (shared,
    global data), a roadmap generation is private to whoever requested
    it, so another user's task_id 404s here rather than leaking status.
    """
    task = get_task(db, task_id, current_user.id)
    if task is None:
        raise NotFoundException("Task not found")

    return RoadmapGenerationStatusResponse(
        task_id=task.id,
        status=task.status,
        roadmap_id=task.roadmap_id,
        error_summary=task.error_summary,
    )


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


@router.patch("/{roadmap_id}/progress", response_model=RoadmapProgressResponse)
def update_roadmap_progress(
    roadmap_id: uuid.UUID,
    payload: RoadmapProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapProgressResponse:
    roadmap = get_roadmap(db, current_user.id, roadmap_id)
    if roadmap is None:
        raise NotFoundException("Roadmap not found")

    step = next((s for s in roadmap.steps if s.get("order") == payload.step_order), None)
    action_items = step.get("action_items", []) if step else []
    if not (0 <= payload.item_index < len(action_items)):
        raise BadRequestException(
            "That step/action item doesn't exist on this roadmap."
        )

    completed = set_action_item_done(
        db,
        roadmap,
        step_order=payload.step_order,
        item_index=payload.item_index,
        done=payload.done,
        interacted_at=payload.interacted_at or datetime.now(timezone.utc),
    )
    db.commit()

    return RoadmapProgressResponse(
        completed_action_items=completed,
        last_interacted_step_order=roadmap.last_interacted_step_order,
    )


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
