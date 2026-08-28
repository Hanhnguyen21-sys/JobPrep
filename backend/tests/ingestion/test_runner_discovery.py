"""Tests for ingestion/runner.py's two entry points --
run_targeted_ingestion (api/routes/jobs.py's on-demand path) and
run_ingestion (the standalone `python -m app.ingestion.runner` path) --
now that both are wired to ingestion/readme.py's discover_postings()
instead of the retired Greenhouse/Lever per-company loop.

Uses `discovered_postings=` to inject a fixed list instead of hitting the
network, and a MagicMock `db`/SessionLocal, same approach the rest of
this suite uses.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.ingestion import runner
from app.ingestion.readme import DiscoveredPosting


def _discovered(**overrides) -> DiscoveredPosting:
    defaults = dict(
        external_id=str(uuid.uuid4()),
        company_name="Acme",
        title="Software Engineer Intern",
        url="https://example.com/1",
        source_updated_at=None,
    )
    defaults.update(overrides)
    return DiscoveredPosting(**defaults)


# ---------------------------------------------------------------------------
# run_targeted_ingestion -- cache hit short-circuits the live fetch
# ---------------------------------------------------------------------------


def test_cache_hit_skips_discovery_and_reports_zero_attempted(monkeypatch):
    fresh_cache_row = MagicMock(last_ingested_at=datetime.now(timezone.utc))
    existing_posting = MagicMock()

    db = MagicMock()
    db.scalar.return_value = fresh_cache_row
    db.scalars.return_value = iter([existing_posting])

    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("must not fetch when cache is fresh")

    monkeypatch.setattr(runner.readme_source, "discover_postings", fail_if_called)

    stats: dict = {}
    result = runner.run_targeted_ingestion(db, "Software Engineer", stats=stats)

    assert called is False
    assert result == [existing_posting]
    assert stats == {"attempted": 0, "succeeded": 0, "failed": 0}


# ---------------------------------------------------------------------------
# run_targeted_ingestion -- live path (stale/missing cache)
# ---------------------------------------------------------------------------


def test_stale_cache_runs_discovery_and_filters_by_position(monkeypatch):
    stale_cache_row = MagicMock(last_ingested_at=datetime.now(timezone.utc) - timedelta(hours=3))
    db = MagicMock()
    db.scalar.return_value = stale_cache_row

    discovered = [
        _discovered(external_id="1", title="Software Engineer Intern", company_name="Acme"),
        _discovered(external_id="2", title="Product Designer Intern", company_name="Other"),
    ]

    company = MagicMock()
    monkeypatch.setattr(runner, "_get_or_create_company_from_posting", lambda db, p: company)

    upserted = []

    def fake_upsert(db, company, posting):
        job_posting = MagicMock(external_id=posting.external_id)
        upserted.append(job_posting)
        return job_posting

    monkeypatch.setattr(runner, "_upsert_discovered_posting", fake_upsert)

    stats: dict = {}
    result = runner.run_targeted_ingestion(
        db, "software engineer", stats=stats, discovered_postings=discovered
    )

    assert len(result) == 1  # only the Software Engineer posting matched
    assert len(upserted) == 1
    assert stats == {"attempted": 1, "succeeded": 1, "failed": 0}


def test_freshness_minutes_zero_always_forces_a_live_pull(monkeypatch):
    """api/routes/jobs.py's background refresh calls this with
    freshness_minutes=0 specifically to bypass the cache -- the freshness
    decision was already made by the caller.
    """
    db = MagicMock()
    # A cache row that WOULD be fresh under a normal freshness window --
    # must be ignored when freshness_minutes=0.
    db.scalar.return_value = MagicMock(last_ingested_at=datetime.now(timezone.utc))

    called = False

    def fake_discover(*a, **k):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(runner.readme_source, "discover_postings", fake_discover)

    runner.run_targeted_ingestion(db, "Software Engineer", freshness_minutes=0)

    assert called is True


def test_discovery_failure_reports_failed_stats_and_empty_result(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None  # no cache row

    def failing_discover(*a, **k):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(runner.readme_source, "discover_postings", failing_discover)

    stats: dict = {}
    result = runner.run_targeted_ingestion(db, "Software Engineer", stats=stats)

    assert result == []
    assert stats == {"attempted": 1, "succeeded": 0, "failed": 1}
    db.rollback.assert_called_once()


def test_position_ingested_marker_is_always_written(monkeypatch):
    """Matches the current simplified behavior (unchanged by this
    rewrite): job_search_cache gets touched after every attempt,
    success or failure, not only on success.
    """
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(runner.readme_source, "discover_postings", lambda: [])

    mark_calls = []
    monkeypatch.setattr(
        runner, "_mark_position_ingested", lambda db, pos: mark_calls.append(pos)
    )

    runner.run_targeted_ingestion(db, "Software Engineer")

    assert mark_calls == ["software engineer"]


# ---------------------------------------------------------------------------
# run_ingestion -- standalone entry point
# ---------------------------------------------------------------------------


def test_run_ingestion_syncs_every_discovered_posting_and_marks_stale(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(runner, "SessionLocal", lambda: db)

    discovered = [_discovered(external_id="1"), _discovered(external_id="2")]

    company = MagicMock()
    monkeypatch.setattr(runner, "_get_or_create_company_from_posting", lambda db, p: company)

    synced_ids = []

    def fake_upsert(db, company, posting):
        synced_ids.append(posting.external_id)
        return MagicMock(external_id=posting.external_id)

    monkeypatch.setattr(runner, "_upsert_discovered_posting", fake_upsert)

    mark_stale_calls = []
    monkeypatch.setattr(
        runner,
        "_mark_stale_postings_inactive",
        lambda db, seen: mark_stale_calls.append(seen),
    )

    runner.run_ingestion(discovered_postings=discovered)

    assert synced_ids == ["1", "2"]
    assert mark_stale_calls == [{"1", "2"}]
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_run_ingestion_rolls_back_on_failure(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(runner, "SessionLocal", lambda: db)

    def failing_discover(*a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(runner.readme_source, "discover_postings", failing_discover)

    runner.run_ingestion()  # must not raise

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    db.close.assert_called_once()
