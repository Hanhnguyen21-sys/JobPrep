"""Tests for api/routes/tracker.py. Route functions are called directly
with a MagicMock `db` (same approach as tests/api/test_jobs_route.py) --
repository-level functions imported into the route module are
monkeypatched rather than exercising real SQL.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.api.routes import tracker as tracker_route
from app.core.exceptions import NotFoundException
from app.models.tracked_job import TrackedJob
from app.models.user import User
from app.schemas.tracked_job import TrackedJobCreateRequest, TrackedJobUpdateRequest


def _fake_user() -> User:
    return User(id=uuid.uuid4(), email="test@example.com")


def _fake_posting(*, is_active: bool = True, url: str | None = "https://example.com/job"):
    posting = MagicMock(title="Software Engineer", url=url, is_active=is_active)
    posting.company.name = "Acme"
    return posting


def _fake_tracked(posting, *, status: str = "saved") -> TrackedJob:
    now = datetime.now(timezone.utc)
    tracked = TrackedJob(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_posting_id=uuid.uuid4(),
        status=status,
        created_at=now,
        updated_at=now,
    )
    tracked.job_posting = posting
    return tracked


def test_create_raises_not_found_when_posting_missing(monkeypatch):
    monkeypatch.setattr(tracker_route, "get_job_postings_by_ids", lambda db, ids: [])

    with pytest.raises(NotFoundException):
        tracker_route.create_tracked_job(
            TrackedJobCreateRequest(job_posting_id=uuid.uuid4()),
            current_user=_fake_user(),
            db=MagicMock(),
        )


def test_create_is_idempotent_and_returns_existing_status(monkeypatch):
    """Selecting an already-tracked posting again must surface its
    current status (e.g. "applied"), not silently reset it to "saved".
    """
    posting = _fake_posting()
    tracked = _fake_tracked(posting, status="applied")

    monkeypatch.setattr(tracker_route, "get_job_postings_by_ids", lambda db, ids: [posting])
    monkeypatch.setattr(
        tracker_route, "get_or_create_tracked_job", lambda db, **kwargs: (tracked, False)
    )

    result = tracker_route.create_tracked_job(
        TrackedJobCreateRequest(job_posting_id=uuid.uuid4()),
        current_user=_fake_user(),
        db=MagicMock(),
    )

    assert result.status == "applied"
    assert result.company_name == "Acme"


def test_create_defaults_new_row_to_saved(monkeypatch):
    posting = _fake_posting()
    tracked = _fake_tracked(posting, status="saved")

    monkeypatch.setattr(tracker_route, "get_job_postings_by_ids", lambda db, ids: [posting])
    monkeypatch.setattr(
        tracker_route, "get_or_create_tracked_job", lambda db, **kwargs: (tracked, True)
    )

    result = tracker_route.create_tracked_job(
        TrackedJobCreateRequest(job_posting_id=uuid.uuid4()),
        current_user=_fake_user(),
        db=MagicMock(),
    )

    assert result.status == "saved"


def test_list_scopes_to_current_user(monkeypatch):
    user = _fake_user()
    captured = {}

    def fake_get_user_tracked_jobs(db, user_id):
        captured["user_id"] = user_id
        return [_fake_tracked(_fake_posting())]

    monkeypatch.setattr(tracker_route, "get_user_tracked_jobs", fake_get_user_tracked_jobs)

    result = tracker_route.list_tracked_jobs(current_user=user, db=MagicMock())

    assert captured["user_id"] == user.id
    assert len(result) == 1


def test_update_raises_not_found_when_not_owned(monkeypatch):
    monkeypatch.setattr(tracker_route, "get_tracked_job", lambda db, uid, tid: None)

    with pytest.raises(NotFoundException):
        tracker_route.update_tracked_job(
            uuid.uuid4(),
            TrackedJobUpdateRequest(status="interview"),
            current_user=_fake_user(),
            db=MagicMock(),
        )


def test_update_applies_new_status(monkeypatch):
    posting = _fake_posting()
    tracked = _fake_tracked(posting, status="saved")

    monkeypatch.setattr(tracker_route, "get_tracked_job", lambda db, uid, tid: tracked)

    def fake_update_status(db, tracked_job, status):
        tracked_job.status = status
        return tracked_job

    monkeypatch.setattr(tracker_route, "update_tracked_job_status", fake_update_status)

    result = tracker_route.update_tracked_job(
        tracked.id,
        TrackedJobUpdateRequest(status="offer"),
        current_user=_fake_user(),
        db=MagicMock(),
    )

    assert result.status == "offer"


def test_delete_raises_not_found_when_not_owned(monkeypatch):
    monkeypatch.setattr(tracker_route, "delete_tracked_job", lambda db, uid, tid: False)

    with pytest.raises(NotFoundException):
        tracker_route.delete_tracked_job_route(
            uuid.uuid4(), current_user=_fake_user(), db=MagicMock()
        )


def test_delete_succeeds_and_commits(monkeypatch):
    monkeypatch.setattr(tracker_route, "delete_tracked_job", lambda db, uid, tid: True)
    db = MagicMock()

    tracker_route.delete_tracked_job_route(uuid.uuid4(), current_user=_fake_user(), db=db)

    db.commit.assert_called_once()


def test_response_reflects_inactive_posting_without_hiding_the_entry():
    """A tracked job must remain visible/editable even after ingestion
    marks its posting inactive -- is_active is surfaced, not filtered.
    """
    posting = _fake_posting(is_active=False)
    tracked = _fake_tracked(posting)

    response = tracker_route._to_response(tracked)

    assert response.is_active is False
    assert response.status == tracked.status
