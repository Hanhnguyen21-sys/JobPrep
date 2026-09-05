"""Job routes.

POST /jobs/match 

  - Fresh cached data exists -> return it immediately, freshness="fresh",
    no background work enqueued.
  - Stale or missing data -> enqueue exactly one background refresh
    (JobSearchTask, deduped by cache_key at the database level -- see
    repositories/job_search_tasks.py) and return immediately: whatever
    matches already exist (possibly none) with freshness="stale" (data
    returned) or "pending" (nothing yet, HTTP 202), plus a task_id.
  - GET /jobs/match/status/{task_id} is how the frontend polls that
    refresh to completion.

"""

import uuid
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.db.session import SessionLocal, get_db
from app.ingestion.query_normalization import cache_key, title_matches_query
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
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
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

# input : a list of job postings and return a list of matched job posting
# job posting - SQLAlchemy model representing data record
# matched job posting: pydantic schema representing data that returns for API
# convert jp into response format called matched jb
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

#check skill gap between user's skills and job postings
# if user has a skill -> marked as True, otherwise -> False
# dict - list of skill that job requires
# have_ids - skills' id of users
# return a list of skill that user has or does not have
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


def _existing_matches(db: Session, target_position: str) -> list[JobPosting]:
    # Broad token-based match, not a raw ILIKE -- see
    # ingestion/query_normalization.title_matches_query for why (near-miss
    # phrasing like "SWE Intern" / "Software Engineering Internship"
    # needs more than substring containment of the whole query phrase).
    # This match runs in Python (token sets + a hand-kept synonym table),
    # so it can't be a SQL WHERE and the LIMIT/OFFSET can't live in the
    # query either -- _page_of_matches slices the result instead.
    candidates = db.scalars(
        select(JobPosting).where(JobPosting.is_active.is_(True))
    )
    return [jp for jp in candidates if title_matches_query(target_position, jp.title)]


def _posting_sort_key(jp: JobPosting) -> datetime:
    """Newest-first ordering key: the ATS's own last-updated timestamp
    when it gave us one, else when we first saw the posting. Explicit so
    page order is stable and meaningful rather than natural DB order.
    """
    return jp.source_updated_at or jp.first_seen_at


def _page_of_matches(
    matches: list[JobPosting], page: int, page_size: int
) -> tuple[list[JobPosting], int, int]:
    """Sort `matches` newest-first and return
    (this page's slice, total_count, total_pages). `page` is 1-indexed;
    a page past the end yields an empty slice with the counts still
    correct -- callers surface that as a valid empty page, not an error.
    """
    total_count = len(matches)
    total_pages = ceil(total_count / page_size) if total_count else 0
    ordered = sorted(matches, key=_posting_sort_key, reverse=True)
    start = (page - 1) * page_size
    return ordered[start : start + page_size], total_count, total_pages


# prepare response to return

def _build_response(
    db: Session,
    current_user: User,
    postings: list[JobPosting],
    freshness: DataFreshness,
    task_id: uuid.UUID | None = None,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JobMatchResponse:
    # Slice to the requested page for `postings`, but aggregate the skill
    # gap over the FULL match set -- it's a property of the whole search,
    # not of whichever page is on screen.
    page_postings, total_count, total_pages = _page_of_matches(postings, page, page_size)
    skill_gap_raw = aggregate_required_skills(db, postings)
    # get skills that a user has
    have_ids = get_user_skill_ids(db, current_user.id)
    # create response with target position, postings info, skill gap
    return JobMatchResponse(
        target_position=current_user.target_position,
        postings=_to_matched_postings(page_postings),
        skill_gap=_to_skill_gap_items(skill_gap_raw, have_ids),
        freshness=freshness,
        task_id=task_id,
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
    )

# run background job to refresh data of specific target position

def _run_refresh_task(task_id: uuid.UUID, desired_position: str) -> None:
   
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
    # 1-indexed page + bounded page size over the full match set. Annotated
    # so the plain int default survives a direct call (tests, other code)
    # while FastAPI still parses/validates them from the query string.
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobMatchResponse:
    if not current_user.target_position:
        raise BadRequestException(
            "No target position set -- submit a resume with a target position first."
        )

    key = cache_key(current_user.target_position)

    cache_row = db.scalar(select(JobSearchCache).where(JobSearchCache.target_position == key))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=FRESHNESS_MINUTES)
    is_fresh = cache_row is not None and cache_row.last_ingested_at >= cutoff

    existing = _existing_matches(db, current_user.target_position)

    if is_fresh:
        return _build_response(
            db, current_user, existing, freshness="fresh",
            page=page, page_size=page_size,
        )


    task, _created = enqueue_or_get_active(db, key)
    db.commit()
    background_tasks.add_task(_run_refresh_task, task.id, current_user.target_position)

    if existing:
        # Stale-while-revalidate: real data now, refresh in the background.
        response.status_code = status.HTTP_200_OK
        return _build_response(
            db, current_user, existing, freshness="stale", task_id=task.id,
            page=page, page_size=page_size,
        )


    response.status_code = status.HTTP_202_ACCEPTED
    return _build_response(
        db, current_user, [], freshness="pending", task_id=task.id,
        page=page, page_size=page_size,
    )


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
