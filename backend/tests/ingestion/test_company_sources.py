"""Tests for the runtime company registry moving from the old
DEFAULT_COMPANIES constant to the `companies` DB table
(see ingestion/runner.py's _get_tracked_companies/_as_company_sources and
their use in run_ingestion()/run_targeted_ingestion()).

No live Postgres is used here -- these are unit tests against mocked
Session/helper objects, not integration tests against the real database.
Company rows referenced in tests are plain in-memory ORM instances
(never flushed/queried), which sidesteps needing a running database or a
SQLite-compatible substitute for the Postgres-specific UUID column type
Company.id uses. See the "Known limitation" note in the final report for
why true DB-integration tests (idempotent seed, real filtering/ordering)
were verified manually against the configured database instead of here.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from app.ingestion import runner
from app.ingestion.runner import CompanySource
from app.models.company import Company


# ---------------------------------------------------------------------------
# _get_tracked_companies -- statement shape (WHERE / ORDER BY)
# ---------------------------------------------------------------------------


class _CapturingDB:
    """Fake Session that just records the statement passed to .scalars()
    instead of executing it against a real database."""

    def __init__(self):
        self.captured_stmt = None

    def scalars(self, stmt):
        self.captured_stmt = stmt
        return iter([])


def test_get_tracked_companies_filters_missing_ats_fields():
    db = _CapturingDB()
    runner._get_tracked_companies(db)

    sql = str(db.captured_stmt)
    assert "ats_platform IS NOT NULL" in sql
    assert "ats_identifier IS NOT NULL" in sql


def test_get_tracked_companies_orders_by_name():
    db = _CapturingDB()
    runner._get_tracked_companies(db)

    sql = str(db.captured_stmt)
    assert "ORDER BY companies.name" in sql


# ---------------------------------------------------------------------------
# _as_company_sources -- Company row -> CompanySource conversion
# ---------------------------------------------------------------------------


def test_as_company_sources_converts_rows_in_order():
    companies = [
        Company(name="Anduril Industries", ats_platform="greenhouse", ats_identifier="andurilindustries"),
        Company(name="Zipline", ats_platform="greenhouse", ats_identifier="flyzipline"),
    ]

    sources = runner._as_company_sources(companies)

    assert sources == [
        CompanySource(name="Anduril Industries", ats_platform="greenhouse", ats_identifier="andurilindustries"),
        CompanySource(name="Zipline", ats_platform="greenhouse", ats_identifier="flyzipline"),
    ]


def test_as_company_sources_empty_list():
    assert runner._as_company_sources([]) == []


# ---------------------------------------------------------------------------
# DEFAULT_COMPANIES must be gone -- no runtime fallback remains
# ---------------------------------------------------------------------------


def test_default_companies_constant_removed():
    assert not hasattr(runner, "DEFAULT_COMPANIES")


# ---------------------------------------------------------------------------
# run_ingestion() -- DB-backed default, override, empty-DB safety
# ---------------------------------------------------------------------------


def test_run_ingestion_uses_db_companies_when_no_override(monkeypatch):
    db_company = Company(name="Cloudflare", ats_platform="greenhouse", ats_identifier="cloudflare")
    monkeypatch.setattr(runner, "_get_tracked_companies", lambda db: [db_company])

    fake_db = MagicMock()
    monkeypatch.setattr(runner, "SessionLocal", lambda: fake_db)

    ingested = []
    monkeypatch.setattr(
        runner,
        "_ingest_company",
        lambda db, source, el, fl: ingested.append(source),
    )

    runner.run_ingestion()

    assert ingested == [
        CompanySource(name="Cloudflare", ats_platform="greenhouse", ats_identifier="cloudflare")
    ]
    fake_db.commit.assert_called_once()
    fake_db.close.assert_called_once()


def test_run_ingestion_explicit_override_bypasses_db_lookup(monkeypatch):
    get_tracked_called = False

    def fake_get_tracked(db):
        nonlocal get_tracked_called
        get_tracked_called = True
        return []

    monkeypatch.setattr(runner, "_get_tracked_companies", fake_get_tracked)
    monkeypatch.setattr(runner, "SessionLocal", lambda: MagicMock())

    ingested = []
    monkeypatch.setattr(
        runner,
        "_ingest_company",
        lambda db, source, el, fl: ingested.append(source),
    )

    override = [CompanySource(name="Manual", ats_platform="greenhouse", ats_identifier="manual")]
    runner.run_ingestion(companies=override)

    assert ingested == override
    assert get_tracked_called is False


def test_run_ingestion_empty_database_makes_no_calls(monkeypatch):
    monkeypatch.setattr(runner, "_get_tracked_companies", lambda db: [])
    fake_db = MagicMock()
    monkeypatch.setattr(runner, "SessionLocal", lambda: fake_db)

    ingest_called = False

    def fake_ingest_company(*args, **kwargs):
        nonlocal ingest_called
        ingest_called = True

    monkeypatch.setattr(runner, "_ingest_company", fake_ingest_company)

    runner.run_ingestion()

    assert ingest_called is False
    fake_db.close.assert_called_once()


def test_run_ingestion_one_company_failure_does_not_stop_others(monkeypatch):
    monkeypatch.setattr(runner, "SessionLocal", lambda: MagicMock())

    sources = [
        CompanySource(name="Bad", ats_platform="greenhouse", ats_identifier="bad"),
        CompanySource(name="Good", ats_platform="greenhouse", ats_identifier="good"),
    ]

    attempted = []

    def fake_ingest_company(db, source, el, fl):
        attempted.append(source.name)
        if source.name == "Bad":
            # An ATS/network-shaped failure -- exactly the category
            # COMPANY_ISOLATABLE_ERRORS exists to isolate per-company.
            raise httpx.ConnectError("simulated ATS outage")

    monkeypatch.setattr(runner, "_ingest_company", fake_ingest_company)

    runner.run_ingestion(companies=sources)

    assert attempted == ["Bad", "Good"]


def test_run_ingestion_does_not_swallow_programming_errors(monkeypatch):
    """A bug in our own code (or a genuine DB error) must NOT be treated
    as an isolatable per-company failure -- COMPANY_ISOLATABLE_ERRORS is
    deliberately narrow (httpx.HTTPError/KeyError/ValueError only), so
    anything else should propagate and fail the whole run loudly.
    """
    monkeypatch.setattr(runner, "SessionLocal", lambda: MagicMock())

    def fake_ingest_company(db, source, el, fl):
        raise RuntimeError("this is a real bug, not an ATS failure")

    monkeypatch.setattr(runner, "_ingest_company", fake_ingest_company)

    with pytest.raises(RuntimeError):
        runner.run_ingestion(
            companies=[CompanySource(name="X", ats_platform="greenhouse", ats_identifier="x")]
        )


def test_run_targeted_ingestion_all_companies_failing_does_not_mark_ingested(monkeypatch):
    """If every company fails, the position must not be cached as
    freshly ingested -- otherwise a repeat search would trust an empty
    result for freshness_minutes instead of retrying sooner.
    """
    monkeypatch.setattr(runner, "_get_tracked_companies", lambda db: [])

    sources = [
        CompanySource(name="A", ats_platform="greenhouse", ats_identifier="a"),
        CompanySource(name="B", ats_platform="lever", ats_identifier="b"),
    ]
    monkeypatch.setattr(
        runner,
        "_fetch_sources_concurrently",
        lambda sources, pos, max_concurrency: [
            runner._FetchResult(source=s, postings=[], error=httpx.ConnectError("simulated ATS outage"))
            for s in sources
        ],
    )

    mark_ingested_called = False

    def fake_mark_ingested(*args, **kwargs):
        nonlocal mark_ingested_called
        mark_ingested_called = True

    monkeypatch.setattr(runner, "_mark_position_ingested", fake_mark_ingested)

    fake_db = MagicMock()
    result = runner.run_targeted_ingestion(
        fake_db, "software engineer", companies=sources, freshness_minutes=0
    )

    assert result == []
    assert mark_ingested_called is False


def test_run_targeted_ingestion_partial_failure_still_marks_ingested_and_returns_matches(
    monkeypatch,
):
    """One company failing (of several) shouldn't discard successful
    matches from the others, and the position IS still marked ingested
    since at least one company actually succeeded.
    """
    from app.models.job_posting import JobPosting

    sources = [
        CompanySource(name="Bad", ats_platform="greenhouse", ats_identifier="bad"),
        CompanySource(name="Good", ats_platform="lever", ats_identifier="good"),
    ]

    def fake_fetch(sources, pos, max_concurrency):
        results = []
        for s in sources:
            if s.name == "Bad":
                results.append(
                    runner._FetchResult(source=s, postings=[], error=httpx.ConnectError("outage"))
                )
            else:
                results.append(runner._FetchResult(source=s, postings=["fake-posting"], error=None))
        return results

    monkeypatch.setattr(runner, "_fetch_sources_concurrently", fake_fetch)
    monkeypatch.setattr(
        runner,
        "_persist_company_postings",
        lambda db, source, postings, el: [JobPosting(title=f"match at {source.name}") for _ in postings],
    )

    mark_ingested_called = False

    def fake_mark_ingested(*args, **kwargs):
        nonlocal mark_ingested_called
        mark_ingested_called = True

    monkeypatch.setattr(runner, "_mark_position_ingested", fake_mark_ingested)

    fake_db = MagicMock()
    result = runner.run_targeted_ingestion(
        fake_db, "software engineer", companies=sources, freshness_minutes=0
    )

    assert len(result) == 1
    assert mark_ingested_called is True


# ---------------------------------------------------------------------------
# run_targeted_ingestion() -- DB-backed default, override, empty-DB safety
# ---------------------------------------------------------------------------


def test_run_targeted_ingestion_uses_db_companies_when_no_override(monkeypatch):
    db_company = Company(name="Cloudflare", ats_platform="greenhouse", ats_identifier="cloudflare")
    monkeypatch.setattr(runner, "_get_tracked_companies", lambda db: [db_company])
    monkeypatch.setattr(runner, "_mark_position_ingested", lambda db, key: None)

    fetched_for = []

    def fake_fetch(sources, pos, max_concurrency):
        fetched_for.extend(sources)
        return [runner._FetchResult(source=s, postings=[], error=None) for s in sources]

    monkeypatch.setattr(runner, "_fetch_sources_concurrently", fake_fetch)
    monkeypatch.setattr(runner, "_persist_company_postings", lambda db, source, postings, el: [])

    fake_db = MagicMock()
    result = runner.run_targeted_ingestion(fake_db, "software engineer", freshness_minutes=0)

    assert fetched_for == [
        CompanySource(name="Cloudflare", ats_platform="greenhouse", ats_identifier="cloudflare")
    ]
    assert result == []


def test_run_targeted_ingestion_explicit_override_bypasses_db_lookup(monkeypatch):
    get_tracked_called = False

    def fake_get_tracked(db):
        nonlocal get_tracked_called
        get_tracked_called = True
        return []

    monkeypatch.setattr(runner, "_get_tracked_companies", fake_get_tracked)
    monkeypatch.setattr(runner, "_mark_position_ingested", lambda db, key: None)

    fetched_for = []

    def fake_fetch(sources, pos, max_concurrency):
        fetched_for.extend(sources)
        return [runner._FetchResult(source=s, postings=[], error=None) for s in sources]

    monkeypatch.setattr(runner, "_fetch_sources_concurrently", fake_fetch)
    monkeypatch.setattr(runner, "_persist_company_postings", lambda db, source, postings, el: [])

    override = [CompanySource(name="Manual", ats_platform="lever", ats_identifier="manual")]
    fake_db = MagicMock()
    runner.run_targeted_ingestion(fake_db, "software engineer", companies=override, freshness_minutes=0)

    assert fetched_for == override
    assert get_tracked_called is False


def test_run_targeted_ingestion_empty_database_is_safe(monkeypatch):
    monkeypatch.setattr(runner, "_get_tracked_companies", lambda db: [])

    fetch_called = False

    def fake_fetch(*args, **kwargs):
        nonlocal fetch_called
        fetch_called = True
        return []

    monkeypatch.setattr(runner, "_fetch_sources_concurrently", fake_fetch)

    mark_ingested_called = False

    def fake_mark_ingested(*args, **kwargs):
        nonlocal mark_ingested_called
        mark_ingested_called = True

    monkeypatch.setattr(runner, "_mark_position_ingested", fake_mark_ingested)

    fake_db = MagicMock()
    result = runner.run_targeted_ingestion(fake_db, "software engineer", freshness_minutes=0)

    assert result == []
    assert fetch_called is False
    assert mark_ingested_called is False
