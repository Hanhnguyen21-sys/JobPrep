"""Roadmap schemas -- request/response shapes for api/routes/roadmaps.py."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import MAX_SELECTED_POSTINGS

# MAX_SELECTED_POSTINGS : can select up to 10 postings

class RoadmapCreateRequest(BaseModel):
    """POST body: the postings the user checked on /jobs (User_Job_Selection).
    Nothing about the selection itself is persisted separately -- see the
    note in db/sql/8_create_roadmaps.sql -- this list is only ever used to
    generate (and then be recorded as the source of) one roadmap.
    """

    job_posting_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=MAX_SELECTED_POSTINGS
    )


class Resource(BaseModel):
    """A course, article, project, certification, or tool suggested for a
    step. `url` is AI-suggested, not verified against a live source --
    services/roadmap.py's generation call has no browsing/search tool
    attached, so a link can be wrong, outdated, or fully hallucinated.
    Nullable so the model isn't forced to fabricate one when it has no
    good guess.
    """

    title: str
    type: Literal["course", "article", "project", "certification", "tool"]
    provider: str | None = None
    url: str | None = None


class RoadmapOverview(BaseModel):
    """Replaces the old free-text `summary` paragraph with the same
    information split into scannable pieces: what to prioritize and how
    long it should take, instead of one dense paragraph.
    """

    headline: str
    priority_skills: list[str]
    estimated_duration: str


class RoadmapStep(BaseModel):
    order: int
    title: str
    focus_skill: str
    skills: list[str]
    why_it_matters: str
    action_items: list[str]
    resources: list[Resource] = []
    project: str | None = None
    duration: str
    success_criteria: list[str]


class RoadmapSourcePosting(BaseModel):
    """Minimal posting info for showing "this roadmap was built from" --
    same shape as schemas/job.py's MatchedJobPosting, but not reusing it
    directly since a roadmap's source posting doesn't carry location/url
    (nothing here needs them) and pulling in schemas/job.py would couple
    the two modules for no real benefit.
    """

    id: uuid.UUID
    company_name: str
    title: str


class RoadmapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Auto-generated label distinguishing this roadmap from others in the
    # user's history (see api/routes/roadmaps.py's _build_title) -- e.g.
    # "Coinbase & 1 more (3 postings) -- Aug 15". Nullable because
    # migration 9 added this column after roadmaps could already exist;
    # older rows have no title. The frontend falls back to
    # "Roadmap for {target_position}" when this is None.
    title: str | None
    target_position: str
    # Replaces the old flat `summary: str`. Always populated by
    # api/routes/roadmaps.py's _to_response, even for roadmaps generated
    # before migration 10 added the `overview` column -- see
    # _legacy_overview there for how those get backfilled at read time.
    overview: RoadmapOverview
    steps: list[RoadmapStep]
    source_postings: list[RoadmapSourcePosting]
    created_at: datetime