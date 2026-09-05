"""Tests for Phase 3 items 9/10: api/routes/jobs.py's database-only,
non-blocking POST /jobs/match and GET /jobs/match/status/{task_id}.

Route functions are called directly (same approach as the rest of this
suite) with a MagicMock `db` and a real `fastapi.BackgroundTasks()` --
`.add_task()` just records the call without executing it (FastAPI only
runs queued background tasks after the response is sent via its own ASGI
machinery), so these tests can assert "exactly one refresh was enqueued"
without a real background task actually running.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks

from app.api.routes import jobs as jobs_route
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.job_search_task import JobSearchTask
from app.models.user import User


def _fake_user(target_position: str | None = "Software Engineer") -> User:
    return User(id=uuid.uuid4(), email="test@example.com", target_position=target_position)


def _stub_aggregation(monkeypatch):
    monkeypatch.setattr(jobs_route, "aggregate_required_skills", lambda db, postings: [])
    monkeypatch.setattr(jobs_route, "get_user_skill_ids", lambda db, uid: set())


def test_no_target_position_raises_bad_request():
    with pytest.raises(BadRequestException):
        jobs_route.find_matching_jobs(
            background_tasks=BackgroundTasks(),
            response=MagicMock(),
            current_user=_fake_user(target_position=None),
            db=MagicMock(),
        )


def test_fresh_data_returns_immediately_without_enqueuing(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = MagicMock(last_ingested_at=datetime.now(timezone.utc))
    monkeypatch.setattr(jobs_route, "_existing_matches", lambda db, needle: [])
    _stub_aggregation(monkeypatch)
    monkeypatch.setattr(
        jobs_route,
        "enqueue_or_get_active",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not enqueue when data is fresh")),
    )

    background_tasks = BackgroundTasks()
    result = jobs_route.find_matching_jobs(
        background_tasks=background_tasks,
        response=MagicMock(),
        current_user=_fake_user(),
        db=db,
    )

    assert result.freshness == "fresh"
    assert result.task_id is None
    assert len(background_tasks.tasks) == 0


def test_stale_data_returns_existing_matches_and_enqueues_one_refresh(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = MagicMock(last_ingested_at=datetime.now(timezone.utc) - timedelta(hours=3))
    fake_posting = MagicMock(id=uuid.uuid4(), title="Software Engineer", location=None, url=None)
    fake_posting.company.name = "Acme"
    monkeypatch.setattr(jobs_route, "_existing_matches", lambda db, needle: [fake_posting])
    _stub_aggregation(monkeypatch)

    fake_task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    monkeypatch.setattr(jobs_route, "enqueue_or_get_active", lambda db, key: (fake_task, True))

    background_tasks = BackgroundTasks()
    response = MagicMock()
    result = jobs_route.find_matching_jobs(
        background_tasks=background_tasks, response=response, current_user=_fake_user(), db=db
    )

    assert result.freshness == "stale"
    assert result.task_id == fake_task.id
    assert len(result.postings) == 1
    assert len(background_tasks.tasks) == 1


def test_no_data_at_all_returns_pending_with_202(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None  # no cache row at all
    monkeypatch.setattr(jobs_route, "_existing_matches", lambda db, needle: [])
    _stub_aggregation(monkeypatch)

    fake_task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    monkeypatch.setattr(jobs_route, "enqueue_or_get_active", lambda db, key: (fake_task, True))

    background_tasks = BackgroundTasks()
    response = MagicMock()
    result = jobs_route.find_matching_jobs(
        background_tasks=background_tasks, response=response, current_user=_fake_user(), db=db
    )

    assert result.freshness == "pending"
    assert result.postings == []
    assert response.status_code == 202
    assert len(background_tasks.tasks) == 1


def test_concurrent_identical_requests_do_not_create_duplicate_tasks(monkeypatch):
    """Simulates two near-simultaneous requests for the same position --
    both call enqueue_or_get_active, which (per
    tests/repositories/test_job_search_tasks.py) the database-level
    unique index guarantees returns the SAME task for the second caller.
    Asserts the route surfaces that same task_id both times, not two.
    """
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(jobs_route, "_existing_matches", lambda db, needle: [])
    _stub_aggregation(monkeypatch)

    shared_task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    call_count = 0

    def fake_enqueue(db, key):
        nonlocal call_count
        call_count += 1
        return shared_task, call_count == 1

    monkeypatch.setattr(jobs_route, "enqueue_or_get_active", fake_enqueue)

    task_ids = {
        jobs_route.find_matching_jobs(
            background_tasks=BackgroundTasks(), response=MagicMock(), current_user=_fake_user(), db=db
        ).task_id
        for _ in range(2)
    }

    assert len(task_ids) == 1


# ---------------------------------------------------------------------------
# Pagination over the match set (page / page_size / total_count / total_pages)
# ---------------------------------------------------------------------------


def _fake_match(title="Software Engineer", updated=None, seen=None):
    jp = MagicMock(
        id=uuid.uuid4(),
        title=title,
        location=None,
        url=None,
        source_updated_at=updated,
        first_seen_at=seen or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    jp.company.name = "Acme"
    return jp


def _fresh_db() -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = MagicMock(last_ingested_at=datetime.now(timezone.utc))
    return db


def _call_match(db, monkeypatch, matches, **kwargs):
    monkeypatch.setattr(jobs_route, "_existing_matches", lambda db, needle: matches)
    _stub_aggregation(monkeypatch)
    return jobs_route.find_matching_jobs(
        background_tasks=BackgroundTasks(),
        response=MagicMock(),
        current_user=_fake_user(),
        db=db,
        **kwargs,
    )


def test_match_first_page_reports_totals(monkeypatch):
    matches = [_fake_match() for _ in range(37)]
    result = _call_match(_fresh_db(), monkeypatch, matches)

    assert len(result.postings) == 15  # DEFAULT_PAGE_SIZE
    assert result.page == 1
    assert result.page_size == 15
    assert result.total_count == 37
    assert result.total_pages == 3


def test_match_second_page_returns_the_offset_slice(monkeypatch):
    # Number the postings by recency so we can assert exactly which slice
    # comes back: newest (highest index) first.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    matches = [
        _fake_match(title=f"SWE {i}", updated=base + timedelta(days=i)) for i in range(37)
    ]
    result = _call_match(_fresh_db(), monkeypatch, matches, page=2)

    assert result.page == 2
    assert [p.title for p in result.postings] == [f"SWE {i}" for i in range(21, 6, -1)]


def test_match_page_past_end_is_empty_not_an_error(monkeypatch):
    matches = [_fake_match() for _ in range(37)]
    result = _call_match(_fresh_db(), monkeypatch, matches, page=99)

    assert result.postings == []
    assert result.total_count == 37
    assert result.total_pages == 3
    assert result.page == 99


def test_match_orders_newest_first_falling_back_to_first_seen(monkeypatch):
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    mid = datetime(2024, 6, 1, tzinfo=timezone.utc)
    new = datetime(2024, 9, 1, tzinfo=timezone.utc)
    a = _fake_match(title="oldest", updated=old)
    b = _fake_match(title="newest", updated=new)
    c = _fake_match(title="no-updated-uses-seen", updated=None, seen=mid)
    result = _call_match(_fresh_db(), monkeypatch, [a, c, b])

    assert [p.title for p in result.postings] == [
        "newest",
        "no-updated-uses-seen",
        "oldest",
    ]


def test_match_custom_page_size_passes_through(monkeypatch):
    matches = [_fake_match() for _ in range(37)]
    result = _call_match(_fresh_db(), monkeypatch, matches, page=2, page_size=5)

    assert result.page_size == 5
    assert len(result.postings) == 5
    assert result.total_pages == 8  # ceil(37 / 5)


def test_skill_gap_aggregates_over_all_matches_not_just_the_page(monkeypatch):
    seen_counts = []
    monkeypatch.setattr(
        jobs_route,
        "aggregate_required_skills",
        lambda db, postings: seen_counts.append(len(postings)) or [],
    )
    monkeypatch.setattr(jobs_route, "get_user_skill_ids", lambda db, uid: set())
    monkeypatch.setattr(
        jobs_route, "_existing_matches", lambda db, needle: [_fake_match() for _ in range(37)]
    )

    jobs_route.find_matching_jobs(
        background_tasks=BackgroundTasks(),
        response=MagicMock(),
        current_user=_fake_user(),
        db=_fresh_db(),
        page=1,
    )

    assert seen_counts == [37]  # full match set, not the 15-item page


def test_get_match_status_404_for_unknown_task():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(NotFoundException):
        jobs_route.get_match_status(task_id=uuid.uuid4(), current_user=_fake_user(), db=db)


def test_get_match_status_full_state_transition():
    """queued -> running -> completed, with data_freshness tracking
    whether job_search_cache has caught up yet."""
    task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db = MagicMock()
    db.get.return_value = task

    db.scalar.return_value = None  # no cache row yet
    result = jobs_route.get_match_status(task_id=task.id, current_user=_fake_user(), db=db)
    assert result.status == "queued"
    assert result.data_freshness == "pending"
    assert result.error_summary is None

    task.status = "running"
    result = jobs_route.get_match_status(task_id=task.id, current_user=_fake_user(), db=db)
    assert result.status == "running"

    task.status = "completed"
    db.scalar.return_value = MagicMock(last_ingested_at=datetime.now(timezone.utc))
    result = jobs_route.get_match_status(task_id=task.id, current_user=_fake_user(), db=db)
    assert result.status == "completed"
    assert result.data_freshness == "fresh"


# ---------------------------------------------------------------------------
# _run_refresh_task -- the actual background execution function
# ---------------------------------------------------------------------------


def _fake_db_for_task(task: JobSearchTask) -> MagicMock:
    db = MagicMock()
    db.get.return_value = task
    return db


def test_run_refresh_task_all_companies_succeed_marks_completed(monkeypatch):
    task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db = _fake_db_for_task(task)
    monkeypatch.setattr(jobs_route, "SessionLocal", lambda: db)

    def fake_ingestion(db, position, freshness_minutes, stats):
        stats.update(attempted=3, succeeded=3, failed=0)
        return []

    monkeypatch.setattr(jobs_route, "run_targeted_ingestion", fake_ingestion)

    jobs_route._run_refresh_task(task.id, "Software Engineer")

    assert task.status == "completed"
    assert task.error_summary is None
    assert task.completed_at is not None


def test_run_refresh_task_partial_failure(monkeypatch):
    task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db = _fake_db_for_task(task)
    monkeypatch.setattr(jobs_route, "SessionLocal", lambda: db)

    def fake_ingestion(db, position, freshness_minutes, stats):
        stats.update(attempted=3, succeeded=2, failed=1)
        return []

    monkeypatch.setattr(jobs_route, "run_targeted_ingestion", fake_ingestion)

    jobs_route._run_refresh_task(task.id, "Software Engineer")

    assert task.status == "partial_failure"
    assert task.error_summary == "1/3 companies failed"


def test_run_refresh_task_all_companies_fail(monkeypatch):
    task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db = _fake_db_for_task(task)
    monkeypatch.setattr(jobs_route, "SessionLocal", lambda: db)

    def fake_ingestion(db, position, freshness_minutes, stats):
        stats.update(attempted=3, succeeded=0, failed=3)
        return []

    monkeypatch.setattr(jobs_route, "run_targeted_ingestion", fake_ingestion)

    jobs_route._run_refresh_task(task.id, "Software Engineer")

    assert task.status == "failed"
    assert task.error_summary == "all 3 companies failed"


def test_run_refresh_task_unexpected_exception_marks_failed_without_leaking_details(monkeypatch):
    task = JobSearchTask(id=uuid.uuid4(), cache_key="v1:software engineer", status="queued")
    db = _fake_db_for_task(task)
    monkeypatch.setattr(jobs_route, "SessionLocal", lambda: db)

    def failing_ingestion(db, position, freshness_minutes, stats):
        raise RuntimeError("postgresql://user:secret@host/db is unreachable")

    monkeypatch.setattr(jobs_route, "run_targeted_ingestion", failing_ingestion)

    jobs_route._run_refresh_task(task.id, "Software Engineer")

    assert task.status == "failed"
    assert "secret" not in task.error_summary
    assert task.error_summary == "RuntimeError during ingestion"


def test_run_refresh_task_missing_task_is_a_noop(monkeypatch):
    db = MagicMock()
    db.get.return_value = None
    monkeypatch.setattr(jobs_route, "SessionLocal", lambda: db)

    ingestion_called = False

    def fake_ingestion(*args, **kwargs):
        nonlocal ingestion_called
        ingestion_called = True

    monkeypatch.setattr(jobs_route, "run_targeted_ingestion", fake_ingestion)

    jobs_route._run_refresh_task(uuid.uuid4(), "Software Engineer")

    assert ingestion_called is False
    db.close.assert_called_once()


def test_get_match_status_never_leaks_raw_exception_text():
    """error_summary must be a sanitized category, never a raw
    exception's str() -- see _run_refresh_task's docstring.
    """
    task = JobSearchTask(
        id=uuid.uuid4(),
        cache_key="v1:software engineer",
        status="failed",
        error_summary="ConnectionError during ingestion",
    )
    db = MagicMock()
    db.get.return_value = task
    db.scalar.return_value = None

    result = jobs_route.get_match_status(task_id=task.id, current_user=_fake_user(), db=db)

    assert "://" not in (result.error_summary or "")  # no leaked connection strings/URLs
    assert "Traceback" not in (result.error_summary or "")
