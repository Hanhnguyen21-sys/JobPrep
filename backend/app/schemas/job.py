"""Job posting schemas -- response shapes for api/routes/jobs.py."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# "fresh" -- cached data is within the freshness window, returned as-is.
# "stale" -- cached data exists but is old; returned immediately anyway
# (stale-while-revalidate) alongside a task_id for the background refresh
# already enqueued. "pending" -- no data exists yet at all; postings/
# skill_gap are empty and the caller should poll task_id until it's done.
DataFreshness = Literal["fresh", "stale", "pending"]

TaskStatus = Literal["queued", "running", "completed", "partial_failure", "failed"]

# Canonical home for the "at most N selected postings" rule -- the
# User_Job_Selection a user makes on /jobs feeds POST /roadmaps
# (schemas/roadmap.py imports this instead of redefining it).
MAX_SELECTED_POSTINGS = 10

# POST /jobs/match result pagination. page_size is deliberately small --
# Step 3's selection UI shows one page at a time, and a broad target
# position ("Software Engineer") can match many hundreds of active
# postings; MAX_PAGE_SIZE bounds a client that asks for too much at once.
# The match filter itself (ingestion.query_normalization.title_matches_
# query) runs in Python, not SQL, so this paginates the response payload
# and the rendered list -- not the underlying active-postings read.
DEFAULT_PAGE_SIZE = 15
MAX_PAGE_SIZE = 50


class MatchedJobPosting(BaseModel):
    id: uuid.UUID
    company_name: str
    title: str
    location: str | None
    url: str | None


class SkillGapItem(BaseModel):
    """One skill required/preferred by at least one matched posting, and
    whether the current user already has it (per their `user_skill` rows).
    A real per-posting match score is services/matching.py's job, later --
    this is the aggregate, lightweight version.
    """

    skill_id: uuid.UUID
    name: str
    category: Literal["technical", "soft"]
    requirement_level: Literal["required", "preferred"]
    user_has: bool


class JobMatchResponse(BaseModel):
    target_position: str
    # `postings` is ONE page (at most `page_size` items) of the full match
    # set -- see the pagination fields below. `skill_gap` is still
    # aggregated across EVERY matched posting, not just this page, so the
    # gap chart doesn't lurch around as the user flips pages.
    postings: list[MatchedJobPosting]
    skill_gap: list[SkillGapItem]
    # See DataFreshness above. task_id is set whenever a background
    # refresh was enqueued (freshness in ("stale", "pending")) -- poll
    # GET /jobs/match/status/{task_id} for completion.
    freshness: DataFreshness
    task_id: uuid.UUID | None = None
    # Pagination over the full match set. `total_count`/`total_pages`
    # describe every posting matching the target position; `postings`
    # above is page `page` of that. Requesting a page past `total_pages`
    # returns an empty `postings` with these counts still correct -- a
    # valid empty page, not an error. Defaults keep older/!test callers
    # that build this without pagination working.
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    total_count: int = 0
    total_pages: int = 0


class JobMatchStatusResponse(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus
    data_freshness: DataFreshness
    last_updated_at: datetime | None
    # Sanitized -- never a raw exception string. None unless status is
    # 'failed'/'partial_failure'.
    error_summary: str | None = None
