"""Tests for Phase 3 item 8: repositories/job_search_tasks.py --
enqueue-with-dedup (including the uniqueness-race fallback path) and
status transitions. MagicMock `db` throughout, no real Postgres.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.models.job_search_task import JobSearchTask
from app.repositories import job_search_tasks as repo


def _assign_id_on_add(obj) -> None:
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.add.side_effect = _assign_id_on_add
    return db


def test_enqueue_creates_new_task_when_none_active():
    db = _fake_db()

    task, created = repo.enqueue_or_get_active(db, "v1:software engineer")

    assert created is True
    assert task.cache_key == "v1:software engineer"
    assert task.status == "queued"
    db.flush.assert_called_once()


def test_enqueue_returns_existing_task_on_uniqueness_race():
    """Simulates two concurrent requests enqueuing the same cache_key --
    the database-level partial unique index
    (uq_job_search_task_active_per_key) rejects the second INSERT, and
    enqueue_or_get_active must return the already-active task instead of
    raising or silently creating a second one.
    """
    db = _fake_db()
    db.flush.side_effect = IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    existing_task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing_task

    task, created = repo.enqueue_or_get_active(db, "v1:software engineer")

    assert created is False
    assert task is existing_task
    db.rollback.assert_called_once()


def test_mark_running_sets_status_and_started_at():
    task = JobSearchTask(id=uuid.uuid4(), cache_key="k", status="queued")
    repo.mark_running(MagicMock(), task)
    assert task.status == "running"
    assert task.started_at is not None


def test_mark_finished_sets_status_completed_at_and_error_summary():
    task = JobSearchTask(id=uuid.uuid4(), cache_key="k", status="running")
    repo.mark_finished(MagicMock(), task, status="failed", error_summary="all 3 companies failed")
    assert task.status == "failed"
    assert task.completed_at is not None
    assert task.error_summary == "all 3 companies failed"


def test_mark_finished_completed_has_no_error_summary():
    task = JobSearchTask(id=uuid.uuid4(), cache_key="k", status="running")
    repo.mark_finished(MagicMock(), task, status="completed")
    assert task.status == "completed"
    assert task.error_summary is None


def test_delete_old_finished_tasks_returns_deleted_count():
    db = MagicMock()
    db.execute.return_value.rowcount = 3
    count = repo.delete_old_finished_tasks(db, older_than=timedelta(days=7))
    assert count == 3
    db.execute.assert_called_once()
