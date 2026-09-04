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
    # _get_cached_matches now filters candidates in Python via
    # title_matches_query (see query_normalization.py), so this needs a
    # real string title, not a bare MagicMock -- it must actually match
    # the "Software Engineer" position searched for below.
    existing_posting = MagicMock(title="Software Engineer Intern")

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

    # Versioned cache_key() format ("v1:software engineer"), not the old
    # bare .strip().lower() -- see the cache-key-consistency tests below
    # for why this specific format matters.
    assert mark_calls == ["v1:software engineer"]


# ---------------------------------------------------------------------------
# Cache-key consistency -- regression coverage for the bug where
# run_targeted_ingestion wrote job_search_cache under a bare
# .strip().lower() key while api/routes/jobs.py's find_matching_jobs read
# it back via query_normalization.cache_key() ("v1:" prefixed). The two
# never matched, so POST /jobs/match's freshness check always saw a cache
# miss and re-enqueued a refresh on every single call. These tests pin
# runner.py to query_normalization's cache_key()/normalize_query(), not a
# hardcoded literal, so they still catch a regression even if
# NORMALIZATION_VERSION is bumped later.
# ---------------------------------------------------------------------------


def test_mark_position_ingested_key_matches_query_normalization_cache_key(monkeypatch):
    """The exact string run_targeted_ingestion hands to
    _mark_position_ingested must be query_normalization.cache_key()'s
    output for the same input -- that's what api/routes/jobs.py's
    find_matching_jobs looks up job_search_cache by (see
    tests/api/test_jobs_route.py for the jobs.py side of this contract).
    """
    from app.ingestion.query_normalization import cache_key

    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(runner.readme_source, "discover_postings", lambda: [])

    mark_calls = []
    monkeypatch.setattr(
        runner, "_mark_position_ingested", lambda db, key: mark_calls.append(key)
    )

    runner.run_targeted_ingestion(db, "Software Engineer")

    assert mark_calls == [cache_key("Software Engineer")]


def test_get_cached_matches_is_looked_up_by_the_same_versioned_key(monkeypatch):
    """A fresh cache row keyed by cache_key(position) must actually be
    found on the next call within freshness_minutes -- exercises the
    write (_mark_position_ingested) and read (_get_cached_matches) sides
    of the same key end to end, through run_targeted_ingestion's two
    calls, rather than just asserting the same string in isolation.
    """
    from app.ingestion.query_normalization import cache_key

    store: dict[str, MagicMock] = {}

    def fake_scalar(stmt):
        # Both the JobSearchCache lookup (_get_cached_matches) and the
        # Company lookup (_get_or_create_company_from_posting) go through
        # db.scalar -- only the cache-row shape matters here, so key off
        # whatever's currently in `store` for the position we're testing.
        return store.get(cache_key("Software Engineer"))

    db = MagicMock()
    db.scalar.side_effect = fake_scalar
    db.scalars.return_value = iter([])

    def fake_mark(db, key):
        store[key] = MagicMock(last_ingested_at=datetime.now(timezone.utc))

    monkeypatch.setattr(runner, "_mark_position_ingested", fake_mark)
    monkeypatch.setattr(runner.readme_source, "discover_postings", lambda: [])

    # First call: no cache row yet -- live path runs, then writes the row.
    runner.run_targeted_ingestion(db, "Software Engineer")
    assert cache_key("Software Engineer") in store

    # Second call: the row just written must now register as a cache hit.
    discover_called = False

    def fail_if_called_again():
        nonlocal discover_called
        discover_called = True
        raise AssertionError("must not re-discover -- the cache row should have hit")

    monkeypatch.setattr(runner.readme_source, "discover_postings", fail_if_called_again)

    stats: dict = {}
    runner.run_targeted_ingestion(db, "Software Engineer", stats=stats)

    assert discover_called is False
    assert stats == {"attempted": 0, "succeeded": 0, "failed": 0}


# ---------------------------------------------------------------------------
# Abbreviation-aware filtering -- regression coverage for the bug where
# _filter_discovered_by_position matched on a bare .strip().lower() needle
# instead of normalize_query(), so an abbreviation like "SWE" never
# matched a title containing "Software Engineer" even though
# query_normalization expands it.
# ---------------------------------------------------------------------------


def test_filter_discovered_by_position_expands_known_abbreviations():
    postings = [
        _discovered(external_id="1", title="Software Engineer Intern", company_name="Acme"),
        _discovered(external_id="2", title="Product Designer Intern", company_name="Other"),
    ]

    filtered = runner._filter_discovered_by_position(postings, "SWE")

    assert [p.external_id for p in filtered] == ["1"]


def test_run_targeted_ingestion_matches_postings_via_abbreviation(monkeypatch):
    """End-to-end through run_targeted_ingestion (not just the filter
    helper) -- a live/stale-cache search for "SWE" must actually sync the
    "Software Engineer Intern" posting, not silently ingest zero matches.
    """
    db = MagicMock()
    db.scalar.return_value = None  # no cache row -- live path runs

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
        db, "SWE", stats=stats, discovered_postings=discovered
    )

    assert len(result) == 1
    assert upserted[0].external_id == "1"
    assert stats == {"attempted": 1, "succeeded": 1, "failed": 0}


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
