"""Tracker routes -- authenticated CRUD over the current user's
tracked_jobs rows.

POST /tracker is the backend half of "reuse the existing job selection
flow": the frontend calls it from hooks/useJobSelection.ts's `toggle`
whenever a posting is newly *selected* on Job Match, not from a separate
"Add to Tracker" control. It's idempotent (get_or_create_tracked_job) so
selecting an already-tracked posting again is a no-op that returns the
existing row -- including its current status -- rather than resetting it
back to "saved". Unselecting on Job Match never calls DELETE here; that
only happens from an explicit Remove action on the Tracker page itself.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.tracked_job import TrackedJob
from app.models.user import User
from app.repositories.jobs import get_job_postings_by_ids
from app.repositories.tracked_jobs import (
    delete_tracked_job,
    get_or_create_tracked_job,
    get_tracked_job,
    get_user_tracked_jobs,
    update_tracked_job_status,
)
from app.schemas.tracked_job import (
    TrackedJobCreateRequest,
    TrackedJobResponse,
    TrackedJobUpdateRequest,
)

router = APIRouter(prefix="/tracker", tags=["tracker"])


def _to_response(tracked: TrackedJob) -> TrackedJobResponse:
    posting = tracked.job_posting
    return TrackedJobResponse(
        id=tracked.id,
        job_posting_id=tracked.job_posting_id,
        company_name=posting.company.name,
        title=posting.title,
        url=posting.url,
        is_active=posting.is_active,
        status=tracked.status,
        created_at=tracked.created_at,
        updated_at=tracked.updated_at,
    )


@router.get("", response_model=list[TrackedJobResponse])
def list_tracked_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TrackedJobResponse]:
    return [_to_response(t) for t in get_user_tracked_jobs(db, current_user.id)]


@router.post("", response_model=TrackedJobResponse, status_code=status.HTTP_201_CREATED)
def create_tracked_job(
    payload: TrackedJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrackedJobResponse:
    postings = get_job_postings_by_ids(db, [payload.job_posting_id])
    if not postings:
        raise NotFoundException("Job posting not found")

    tracked, _created = get_or_create_tracked_job(
        db, user_id=current_user.id, job_posting_id=payload.job_posting_id
    )
    db.commit()
    db.refresh(tracked)
    return _to_response(tracked)


@router.patch("/{tracked_job_id}", response_model=TrackedJobResponse)
def update_tracked_job(
    tracked_job_id: uuid.UUID,
    payload: TrackedJobUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrackedJobResponse:
    tracked = get_tracked_job(db, current_user.id, tracked_job_id)
    if tracked is None:
        raise NotFoundException("Tracked job not found")

    update_tracked_job_status(db, tracked, payload.status)
    db.commit()
    db.refresh(tracked)
    return _to_response(tracked)


@router.delete("/{tracked_job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracked_job_route(
    tracked_job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Removes only this user's tracking row -- the shared job_postings
    row it points at is untouched, so the posting stays visible/selectable
    on Job Match. Doing this again for the same posting later creates a
    brand new tracked_jobs row (via POST /tracker) rather than reviving
    this one.
    """
    deleted = delete_tracked_job(db, current_user.id, tracked_job_id)
    if not deleted:
        raise NotFoundException("Tracked job not found")
    db.commit()
