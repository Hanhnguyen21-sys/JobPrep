"""Tests for api/routes/roadmaps.py's background POST /roadmaps flow:
create_roadmap_from_selection (enqueue, always 202 now),
get_roadmap_generation_status (polled), and _run_roadmap_generation_task
(the actual background execution) -- mirrors
tests/api/test_jobs_route.py's shape for the equivalent /jobs/match flow.

Route functions are called directly with a MagicMock `db` and a real
fastapi.BackgroundTasks() (`.add_task()` just records the call), same
approach as the rest of this suite.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks

from app.api.routes import roadmaps as roadmaps_route
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.roadmap_generation_task import RoadmapGenerationTask
from app.models.user import User


def _fake_user(target_position: str | None = "Software Engineer") -> User:
    return User(id=uuid.uuid4(), email="test@example.com", target_position=target_position)


def _fake_posting(posting_id: uuid.UUID) -> MagicMock:
    posting = MagicMock(id=posting_id)
    posting.company.name = "Acme"
    return posting


# ---------------------------------------------------------------------------
# create_roadmap_from_selection -- enqueue path
# ---------------------------------------------------------------------------


def test_no_target_position_raises_bad_request():
    payload = MagicMock(job_posting_ids=[uuid.uuid4()])
    with pytest.raises(BadRequestException):
        roadmaps_route.create_roadmap_from_selection(
            payload,
            background_tasks=BackgroundTasks(),
            current_user=_fake_user(target_position=None),
            db=MagicMock(),
        )


def test_missing_posting_raises_bad_request_before_enqueueing(monkeypatch):
    requested_id = uuid.uuid4()
    payload = MagicMock(job_posting_ids=[requested_id])

    monkeypatch.setattr(roadmaps_route, "get_job_postings_by_ids", lambda db, ids: [])

    enqueue_called = False

    def fake_create_task(db, **kwargs):
        nonlocal enqueue_called
        enqueue_called = True

    monkeypatch.setattr(roadmaps_route, "create_task", fake_create_task)

    with pytest.raises(BadRequestException):
        roadmaps_route.create_roadmap_from_selection(
            payload,
            background_tasks=BackgroundTasks(),
            current_user=_fake_user(),
            db=MagicMock(),
        )

    assert enqueue_called is False


def test_valid_selection_enqueues_exactly_one_background_task(monkeypatch):
    posting_id = uuid.uuid4()
    payload = MagicMock(job_posting_ids=[posting_id])

    monkeypatch.setattr(
        roadmaps_route, "get_job_postings_by_ids", lambda db, ids: [_fake_posting(posting_id)]
    )

    fake_task = RoadmapGenerationTask(id=uuid.uuid4(), user_id=uuid.uuid4(), job_posting_ids=[posting_id])
    monkeypatch.setattr(roadmaps_route, "create_task", lambda db, **kwargs: fake_task)

    background_tasks = BackgroundTasks()
    result = roadmaps_route.create_roadmap_from_selection(
        payload, background_tasks=background_tasks, current_user=_fake_user(), db=MagicMock()
    )

    assert result.task_id == fake_task.id
    assert len(background_tasks.tasks) == 1


def test_duplicate_ids_deduped_before_lookup(monkeypatch):
    posting_id = uuid.uuid4()
    payload = MagicMock(job_posting_ids=[posting_id, posting_id, posting_id])

    looked_up_ids = []

    def fake_lookup(db, ids):
        looked_up_ids.extend(ids)
        return [_fake_posting(posting_id)]

    monkeypatch.setattr(roadmaps_route, "get_job_postings_by_ids", fake_lookup)

    fake_task = RoadmapGenerationTask(id=uuid.uuid4(), user_id=uuid.uuid4(), job_posting_ids=[posting_id])
    monkeypatch.setattr(roadmaps_route, "create_task", lambda db, **kwargs: fake_task)

    roadmaps_route.create_roadmap_from_selection(
        payload, background_tasks=BackgroundTasks(), current_user=_fake_user(), db=MagicMock()
    )

    assert looked_up_ids == [posting_id]  # deduped, not sent three times


# ---------------------------------------------------------------------------
# get_roadmap_generation_status
# ---------------------------------------------------------------------------


def test_status_404_for_unknown_task(monkeypatch):
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: None)

    with pytest.raises(NotFoundException):
        roadmaps_route.get_roadmap_generation_status(
            task_id=uuid.uuid4(), current_user=_fake_user(), db=MagicMock()
        )


def test_status_is_scoped_to_current_user(monkeypatch):
    """A task belonging to a different user must read back as 404, not
    leak that user's generation status -- unlike JobSearchTask, roadmap
    generation is private per-user (see get_task's docstring).
    """
    seen_args = {}

    def fake_get_task(db, task_id, user_id):
        seen_args["task_id"] = task_id
        seen_args["user_id"] = user_id
        return None  # simulates "exists, but not owned by this user"

    monkeypatch.setattr(roadmaps_route, "get_task", fake_get_task)

    user = _fake_user()
    task_id = uuid.uuid4()
    with pytest.raises(NotFoundException):
        roadmaps_route.get_roadmap_generation_status(task_id=task_id, current_user=user, db=MagicMock())

    assert seen_args == {"task_id": task_id, "user_id": user.id}


def test_status_reports_completed_with_roadmap_id(monkeypatch):
    roadmap_id = uuid.uuid4()
    task = RoadmapGenerationTask(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_posting_ids=[uuid.uuid4()],
        status="completed",
        roadmap_id=roadmap_id,
    )
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: task)

    result = roadmaps_route.get_roadmap_generation_status(
        task_id=task.id, current_user=_fake_user(), db=MagicMock()
    )

    assert result.status == "completed"
    assert result.roadmap_id == roadmap_id
    assert result.error_summary is None


# ---------------------------------------------------------------------------
# _run_roadmap_generation_task -- the actual background execution function
# ---------------------------------------------------------------------------


def _fake_db_for_task(task: RoadmapGenerationTask, user: User) -> MagicMock:
    db = MagicMock()

    def fake_get(model, obj_id):
        return user if obj_id == user.id else None

    db.get.side_effect = fake_get
    return db


def test_run_generation_task_success_marks_completed(monkeypatch):
    user = _fake_user()
    posting_id = uuid.uuid4()
    task = RoadmapGenerationTask(id=uuid.uuid4(), user_id=user.id, job_posting_ids=[posting_id], status="queued")

    db = _fake_db_for_task(task, user)
    monkeypatch.setattr(roadmaps_route, "SessionLocal", lambda: db)
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: task)
    monkeypatch.setattr(
        roadmaps_route, "get_job_postings_by_ids", lambda db, ids: [_fake_posting(posting_id)]
    )
    monkeypatch.setattr(roadmaps_route, "_ensure_descriptions", lambda db, postings: None)
    db.scalars.return_value = iter([])  # existing_skill_names query

    fake_roadmap = MagicMock(id=uuid.uuid4())
    monkeypatch.setattr(roadmaps_route, "create_roadmap", lambda db, **kwargs: fake_roadmap)

    fake_result = MagicMock()
    fake_result.overview.headline = "Headline"
    fake_result.overview.model_dump.return_value = {}
    fake_result.steps = []
    monkeypatch.setattr(roadmaps_route, "generate_roadmap", lambda **kwargs: fake_result)

    roadmaps_route._run_roadmap_generation_task(task.id, user.id, [posting_id])

    assert task.status == "completed"
    assert task.roadmap_id == fake_roadmap.id
    assert task.error_summary is None


def test_run_generation_task_llm_returns_none_marks_failed(monkeypatch):
    user = _fake_user()
    posting_id = uuid.uuid4()
    task = RoadmapGenerationTask(id=uuid.uuid4(), user_id=user.id, job_posting_ids=[posting_id], status="queued")

    db = _fake_db_for_task(task, user)
    monkeypatch.setattr(roadmaps_route, "SessionLocal", lambda: db)
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: task)
    monkeypatch.setattr(
        roadmaps_route, "get_job_postings_by_ids", lambda db, ids: [_fake_posting(posting_id)]
    )
    monkeypatch.setattr(roadmaps_route, "_ensure_descriptions", lambda db, postings: None)
    db.scalars.return_value = iter([])
    monkeypatch.setattr(roadmaps_route, "generate_roadmap", lambda **kwargs: None)

    roadmaps_route._run_roadmap_generation_task(task.id, user.id, [posting_id])

    assert task.status == "failed"
    assert task.roadmap_id is None
    assert task.error_summary is not None


def test_run_generation_task_unexpected_exception_marks_failed_without_leaking_details(monkeypatch):
    user = _fake_user()
    posting_id = uuid.uuid4()
    task = RoadmapGenerationTask(id=uuid.uuid4(), user_id=user.id, job_posting_ids=[posting_id], status="queued")

    db = _fake_db_for_task(task, user)
    monkeypatch.setattr(roadmaps_route, "SessionLocal", lambda: db)
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: task)

    def failing_lookup(db, ids):
        raise RuntimeError("postgresql://user:secret@host/db is unreachable")

    monkeypatch.setattr(roadmaps_route, "get_job_postings_by_ids", failing_lookup)

    roadmaps_route._run_roadmap_generation_task(task.id, user.id, [posting_id])

    assert task.status == "failed"
    assert "secret" not in task.error_summary
    assert task.error_summary == "RuntimeError during roadmap generation"


def test_run_generation_task_missing_task_is_a_noop(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(roadmaps_route, "SessionLocal", lambda: db)
    monkeypatch.setattr(roadmaps_route, "get_task", lambda db, task_id, user_id: None)

    lookup_called = False

    def fake_lookup(db, ids):
        nonlocal lookup_called
        lookup_called = True
        return []

    monkeypatch.setattr(roadmaps_route, "get_job_postings_by_ids", fake_lookup)

    roadmaps_route._run_roadmap_generation_task(uuid.uuid4(), uuid.uuid4(), [uuid.uuid4()])

    assert lookup_called is False
    db.close.assert_called_once()
