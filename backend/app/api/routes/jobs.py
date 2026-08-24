"""Job routes.

POST /jobs/match is database-only and non-blocking (Phase 3 of the
/jobs/match latency work -- see ingestion/runner.py's module docstring
for Phases 1-2). It never calls Greenhouse/Lever/OpenAI itself:

  - Fresh cached data exists -> return it immediately, freshness="fresh",
    no background work enqueued.
  - Stale or missing data -> enqueue exactly one background refresh
    (JobSearchTask, deduped by cache_key at the database level -- see
    repositories/job_search_tasks.py) and return immediately: whatever
    matches already exist (possibly none) with freshness="stale" (data
    returned) or "pending" (nothing yet, HTTP 202), plus a task_id.
  - GET /jobs/match/status/{task_id} is how the frontend polls that
    refresh to completion.

The actual live ATS+OpenAI pipeline (ingestion/runner.py's
run_targeted_ingestion) now only ever runs inside _run_refresh_task, via
FastAPI's BackgroundTasks -- see that function's docstring for its
durability caveat (in-process, not a separate durable worker; revisit
with a real queue if refresh volume/reliability needs grow).
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.db.session import SessionLocal, get_db
from app.ingestion.query_normalization import cache_key, normalize_query
from app.ingestion.runner import run_targeted_ingestion
from app.models.job_posting import JobPosting
from app.models.search_cache import JobSearchCache
from app.models.user import User
from app.repositories.job_search_tasks import (
    enqueue_or_get_active,
    get_task,
    mark_finished,
    mark_running,
)
from app.repositories.jobs import aggregate_required_skills, get_user_skill_ids
from app.schemas.job import (
    DataFreshness,
    JobMatchResponse,
    JobMatchStatusResponse,
    MatchedJobPosting,
    SkillGapItem,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# How long a job_search_cache entry counts as "fresh" -- same window
# run_targeted_ingestion's freshness_minutes used to gate the (now
# retired) synchronous live-pull path.
FRESHNESS_MINUTES = 60


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


def _existing_matches(db: Session, needle: str) -> list[JobPosting]:
    """Whatever's already in job_postings for this (normalized) query --
    the database-only read POST /jobs/match now always does first,
    regardless of freshness.
    """
    return list(
        db.scalars(
            select(JobPosting).where(
                JobPosting.title.ilike(f"%{needle}%"),
                JobPosting.is_active.is_(True),
            )
        )
    )


def _build_response(
    db: Session,
    current_user: User,
    postings: list[JobPosting],
    freshness: DataFreshness,
    task_id: uuid.UUID | None = None,
) -> JobMatchResponse:
    skill_gap_raw = aggregate_required_skills(db, postings)
    have_ids = get_user_skill_ids(db, current_user.id)
    return JobMatchResponse(
        target_position=current_user.target_position,
        postings=_to_matched_postings(postings),
        skill_gap=_to_skill_gap_items(skill_gap_raw, have_ids),
        freshness=freshness,
        task_id=task_id,
    )


def _run_refresh_task(task_id: uuid.UUID, desired_position: str) -> None:
    """Runs via FastAPI BackgroundTasks, after the response for the
    request that enqueued it has already been sent. Opens its own DB
    session (same pattern as ingestion/runner.py's run_ingestion()
    standalone-script usage) since it must outlive that request's
    session/lifecycle.

    Durability caveat (see also models/job_search_task.py): BackgroundTasks
    runs in-process on the same web server -- if the process crashes or
    restarts while this is mid-flight, the task is simply lost (stuck at
    'running', no automatic resume/retry). Acceptable at this app's
    current scale; swap for a real queue (RQ/Celery+Redis, ARQ) if that
    changes. Idempotent either way: re-running run_targeted_ingestion for
    the same position is always safe (upserts + description_hash gating),
    so a manual retry (re-enqueue) after a stuck task is harmless.
    """
    db = SessionLocal()
    try:
        task = get_task(db, task_id)
        if task is None:
            return

        mark_running(db, task)
        db.commit()

        stats: dict = {}
        try:
            run_targeted_ingestion(db, desired_position, freshness_minutes=0, stats=stats)
        except Exception as exc:  # noqa: BLE001 -- genuinely unexpected (a bug or DB error),
            # not a per-company failure (those are isolated inside
            # run_targeted_ingestion itself and reflected via `stats`).
            # Never include str(exc) here -- only the exception's type
            # name, so a stray secret/path in an error message can't leak
            # through this public-facing status field.
            mark_finished(
                db, task, status="failed", error_summary=f"{type(exc).__name__} during ingestion"
            )
            db.commit()
            return

        attempted = stats.get("attempted", 0)
        failed = stats.get("failed", 0)
        succeeded = stats.get("succeeded", 0)

        if attempted == 0 or failed == 0:
            mark_finished(db, task, status="completed")
        elif succeeded > 0:
            mark_finished(
                db, task, status="partial_failure", error_summary=f"{failed}/{attempted} companies failed"
            )
        else:
            mark_finished(db, task, status="failed", error_summary=f"all {attempted} companies failed")
        db.commit()
    finally:
        db.close()


@router.post("/match", response_model=JobMatchResponse)
def find_matching_jobs(
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobMatchResponse:
    if not current_user.target_position:
        raise BadRequestException(
            "No target position set -- submit a resume with a target position first."
        )

    key = cache_key(current_user.target_position)
    needle = normalize_query(current_user.target_position)

    cache_row = db.scalar(select(JobSearchCache).where(JobSearchCache.target_position == key))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=FRESHNESS_MINUTES)
    is_fresh = cache_row is not None and cache_row.last_ingested_at >= cutoff

    existing = _existing_matches(db, needle)

    if is_fresh:
        return _build_response(db, current_user, existing, freshness="fresh")

    # Stale or never-ingested -- enqueue exactly one refresh. Deduped at
    # the database level (a partial unique index on
    # (cache_key) WHERE status IN ('queued','running')), so two
    # concurrent requests for the same position can never create two
    # active tasks.
    task, _created = enqueue_or_get_active(db, key)
    db.commit()
    background_tasks.add_task(_run_refresh_task, task.id, current_user.target_position)

    if existing:
        # Stale-while-revalidate: real data now, refresh in the background.
        response.status_code = status.HTTP_200_OK
        return _build_response(db, current_user, existing, freshness="stale", task_id=task.id)

    # Nothing at all yet -- 202 Accepted: the request was accepted and is
    # being processed, but there's no result to represent yet (as
    # opposed to 200, which would misleadingly imply "here are your zero
    # matches" when really "we haven't looked yet").
    response.status_code = status.HTTP_202_ACCEPTED
    return _build_response(db, current_user, [], freshness="pending", task_id=task.id)


@router.get("/match/status/{task_id}", response_model=JobMatchStatusResponse)
def get_match_status(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobMatchStatusResponse:
    """Polled by the frontend after a "stale"/"pending" POST /jobs/match
    response until `status` reaches a terminal state (completed/
    partial_failure/failed), then re-calls POST /jobs/match to pick up
    the refreshed data. Not user-scoped -- JobSearchTask is keyed by
    cache_key, shared across all users the same way job_search_cache/
    job_postings already are (see ingestion/runner.py's module
    docstring); `current_user` here is only an auth requirement, not an
    ownership filter.
    """
    task = get_task(db, task_id)
    if task is None:
        raise NotFoundException("Task not found")

    cache_row = db.scalar(
        select(JobSearchCache).where(JobSearchCache.target_position == task.cache_key)
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=FRESHNESS_MINUTES)
    data_freshness: DataFreshness
    if cache_row is not None and cache_row.last_ingested_at >= cutoff:
        data_freshness = "fresh"
    elif cache_row is not None:
        data_freshness = "stale"
    else:
        data_freshness = "pending"

    return JobMatchStatusResponse(
        task_id=task.id,
        status=task.status,
        data_freshness=data_freshness,
        last_updated_at=cache_row.last_ingested_at if cache_row else None,
        error_summary=task.error_summary,
    )
