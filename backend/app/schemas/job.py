"""Job posting schemas -- response shapes for api/routes/jobs.py."""

import uuid
from typing import Literal

from pydantic import BaseModel

# Canonical home for the "at most N selected postings" rule -- the
# User_Job_Selection a user makes on /jobs feeds POST /roadmaps
# (schemas/roadmap.py imports this instead of redefining it).
MAX_SELECTED_POSTINGS = 10


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
    postings: list[MatchedJobPosting]
    skill_gap: list[SkillGapItem]
