"""Resume submission + skill-extraction schemas.

There is deliberately no `Resume` DB model (see file-structure-plan.md) —
resume text is submitted, sent to the AI for extraction, and then
discarded. Only the *skills it produces* get persisted, into `Skill` and
the `user_skill` join table. These are request/response shapes for that
flow, not a model backed by its own table.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ResumeSubmit(BaseModel):
    """POST body: raw resume text, plus the position the user is looking
    for. `target_position` is saved onto the user's profile (see
    api/routes/resumes.py) so a later "Find Matching Jobs" call
    (api/routes/jobs.py) doesn't need it re-sent.
    """

    text: str = Field(min_length=1, max_length=20_000)
    target_position: str = Field(min_length=1, max_length=200)


class SkillWithContext(BaseModel):
    """A skill now linked to the user, plus its estimated proficiency.

    Built by hand in the route (not straight from an ORM object) since
    proficiency_level/proficiency_confidence live on `user_skill`, not on
    `Skill` itself — the route joins the two before returning this.
    """

    id: uuid.UUID
    name: str
    category: Literal["technical", "soft"]
    proficiency_level: int = Field(ge=0, le=100)
    proficiency_confidence: Literal["low", "medium", "high"]


class ResumeSkillsResponse(BaseModel):
    """What the frontend gets back: the skills now linked to this user,
    each with an estimated proficiency — lets the UI show the user how
    strong each extracted skill looks based on their resume.
    """

    skills: list[SkillWithContext]
