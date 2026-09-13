"""Tests for repositories/tracked_jobs.py -- the Tracker page's
persistence layer. MagicMock `db` throughout, no real Postgres, same
convention as tests/repositories/test_jobs.py.
"""

import uuid
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.repositories import tracked_jobs as repo


def test_creates_a_new_row_when_none_exists():
    db = MagicMock()
    db.scalar.return_value = None  # no existing row
    user_id, job_posting_id = uuid.uuid4(), uuid.uuid4()

    tracked, created = repo.get_or_create_tracked_job(
        db, user_id=user_id, job_posting_id=job_posting_id
    )

    assert created is True
    assert tracked.user_id == user_id
    assert tracked.job_posting_id == job_posting_id
    assert tracked.status == "saved"
    db.add.assert_called_once_with(tracked)
    db.flush.assert_called_once()


def test_returns_existing_row_unchanged_when_already_tracked():
    """Re-selecting an already-tracked posting on Job Match must not
    reset a status the user has already progressed (e.g. "applied") back
    to "saved" -- this is the idempotency the whole feature depends on.
    """
    db = MagicMock()
    existing = MagicMock(status="applied")
    db.scalar.return_value = existing

    tracked, created = repo.get_or_create_tracked_job(
        db, user_id=uuid.uuid4(), job_posting_id=uuid.uuid4()
    )

    assert created is False
    assert tracked is existing
    assert tracked.status == "applied"
    db.add.assert_not_called()


def test_concurrent_insert_race_returns_the_winner_instead_of_raising():
    """Two near-simultaneous selects of the same posting: the first
    db.scalar() lookup finds nothing for both, but only one INSERT can
    win against uq_tracked_jobs_user_job -- the loser's flush() raises
    IntegrityError, which must be caught and resolved by re-fetching
    rather than propagating.
    """
    db = MagicMock()
    winner = MagicMock(status="saved")
    # First call (the initial existence check): no row yet.
    # Second call (post-IntegrityError re-fetch): the winner's row.
    db.scalar.side_effect = [None, winner]
    db.flush.side_effect = IntegrityError("insert", {}, Exception("unique violation"))

    tracked, created = repo.get_or_create_tracked_job(
        db, user_id=uuid.uuid4(), job_posting_id=uuid.uuid4()
    )

    assert created is False
    assert tracked is winner
    db.rollback.assert_called_once()


def test_delete_returns_false_when_not_found_or_not_owned():
    db = MagicMock()
    db.scalar.return_value = None

    deleted = repo.delete_tracked_job(db, uuid.uuid4(), uuid.uuid4())

    assert deleted is False
    db.delete.assert_not_called()


def test_delete_removes_only_the_matching_row():
    db = MagicMock()
    row = MagicMock()
    db.scalar.return_value = row

    deleted = repo.delete_tracked_job(db, uuid.uuid4(), uuid.uuid4())

    assert deleted is True
    db.delete.assert_called_once_with(row)
    db.flush.assert_called_once()


def test_update_status_sets_status_and_flushes():
    db = MagicMock()
    tracked = MagicMock(status="saved")

    result = repo.update_tracked_job_status(db, tracked, "interview")

    assert result.status == "interview"
    db.flush.assert_called_once()
