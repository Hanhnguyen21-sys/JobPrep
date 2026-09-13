"""Tracker schemas -- request/response shapes for api/routes/tracker.py."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Mirrors app/models/tracked_job.py's TRACKED_JOB_STATUSES and
# frontend/src/types/tracker.ts's TrackedJobStatus -- keep all three in
# sync by hand, same convention as schemas/job.py's MAX_SELECTED_POSTINGS.
TrackedJobStatus = Literal[
    "saved", "applied", "interview", "offer", "rejected", "withdrawn"
]


class TrackedJobCreateRequest(BaseModel):
    job_posting_id: uuid.UUID


class TrackedJobUpdateRequest(BaseModel):
    status: TrackedJobStatus


class TrackedJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_posting_id: uuid.UUID
    company_name: str
    title: str
    url: str | None
    # The underlying posting's current JobPosting.is_active -- read live at
    # response time so a Tracker entry can flag "no longer active" without
    # ever being deleted itself (ingestion never deletes job_postings
    # rows, only flips this flag -- see app/ingestion/runner.py).
    is_active: bool
    status: TrackedJobStatus
    created_at: datetime
    updated_at: datetime
