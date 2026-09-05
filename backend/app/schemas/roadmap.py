"""Roadmap schemas -- request/response shapes for api/routes/roadmaps.py."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import MAX_SELECTED_POSTINGS

# A roadmap is built from at most MAX_SELECTED_POSTINGS selected postings
# (defined in schemas/job.py) -- enforced on the request below.

class RoadmapCreateRequest(BaseModel):

    job_posting_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=MAX_SELECTED_POSTINGS
    )


RoadmapTaskStatus = Literal["queued", "running", "completed", "failed"]


class RoadmapGenerationAcceptedResponse(BaseModel):
    """POST /roadmaps' response -- always 202, since generation always
    runs in the background now (see api/routes/roadmaps.py). Poll
    GET /roadmaps/status/{task_id} for completion.
    """

    task_id: uuid.UUID


class RoadmapGenerationStatusResponse(BaseModel):
    task_id: uuid.UUID
    status: RoadmapTaskStatus
    # Set once status == "completed" -- fetch the full roadmap via
    # GET /roadmaps/{roadmap_id}, same split as JobMatchStatusResponse
    # (status + pointer, not the payload itself).
    roadmap_id: uuid.UUID | None = None
    # Sanitized -- never a raw exception string. None unless status is
    # "failed".
    error_summary: str | None = None


class Resource(BaseModel):

    title: str
    type: Literal["course", "article", "project", "certification", "tool"]
    provider: str | None = None
    url: str | None = None


class PrioritySkill(BaseModel):
   

    skill: str
    current_level: int
    target_level: int


class RoadmapOverview(BaseModel):
    
    headline: str
    priority_skills: list[PrioritySkill]
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
  

    id: uuid.UUID
    company_name: str
    title: str


class RoadmapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    title: str | None
    target_position: str

    overview: RoadmapOverview
    steps: list[RoadmapStep]
    source_postings: list[RoadmapSourcePosting]
    created_at: datetime
    # {"<step_order>": [<action_item index>, ...]} -- see
    # models/roadmap.py's Roadmap.completed_action_items. Empty for rows
    # with nothing checked off yet (the route coerces null to {}).
    completed_action_items: dict[str, list[int]] = {}
    # Which step the user most recently checked/unchecked an action item
    # on -- see models/roadmap.py's Roadmap.last_interacted_step_order.
    # None if no interaction has ever been recorded; the Dashboard falls
    # back to its old "first incomplete step" logic in that case.
    last_interacted_step_order: int | None = None


class RoadmapProgressUpdate(BaseModel):
    step_order: int = Field(ge=1)
    item_index: int = Field(ge=0)
    done: bool
    # When the user actually made this change, client-side -- lets the
    # backend tell a genuinely newer interaction apart from an older
    # request that happens to arrive/resolve later (see
    # repositories/roadmaps.py's set_action_item_done). Optional so an
    # older client build still works; the route falls back to server time.
    interacted_at: datetime | None = None


class RoadmapProgressResponse(BaseModel):
    completed_action_items: dict[str, list[int]]
    last_interacted_step_order: int | None = None