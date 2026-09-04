"""Tests for ingestion/runner.py's discovery-upsert and skill-extraction
helpers.

Rewritten for Phase 2 (README-based discovery replacing Greenhouse/Lever):
_upsert_job_posting (NormalizedJobPosting-keyed) no longer exists --
_upsert_discovered_posting (DiscoveredPosting-keyed) replaced it. The
critical new behavior this file covers: a discovery upsert must never
touch `description`/`description_hash` -- discovery never has a
description (see ingestion/readme.py's module docstring), and a selected
posting's description (fetched later by api/routes/roadmaps.py) must
survive every later discovery re-run instead of getting wiped back to
None by it.

Uses a MagicMock `db` (no real Postgres), same approach the rest of this
suite already uses.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.ingestion import runner
from app.ingestion.readme import DiscoveredPosting
from app.models.company import Company
from app.models.job_posting import JobPosting


def _discovered(**overrides) -> DiscoveredPosting:
    defaults = dict(
        external_id="ext-1",
        company_name="Acme",
        title="Software Engineer Intern",
        url="https://example.com/1",
        source_updated_at=None,
    )
    defaults.update(overrides)
    return DiscoveredPosting(**defaults)


def _fake_db(existing_job_posting: JobPosting | None) -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = existing_job_posting
    return db


def _company() -> Company:
    return Company(id=uuid.uuid4(), name="Acme", ats_platform=runner.SOURCE_PLATFORM, ats_identifier="Acme")


# ---------------------------------------------------------------------------
# _upsert_discovered_posting: new / metadata refresh / description preserved
# ---------------------------------------------------------------------------


def test_new_posting_is_created_with_no_description():
    db = _fake_db(existing_job_posting=None)
    job_posting = runner._upsert_discovered_posting(db, _company(), _discovered())

    assert job_posting.title == "Software Engineer Intern"
    assert job_posting.url == "https://example.com/1"
    assert job_posting.description is None  # discovery never sets it


def test_existing_posting_gets_metadata_refreshed():
    existing = JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-1",
        title="Old Title",
        url="https://example.com/old",
        is_active=False,
    )
    db = _fake_db(existing_job_posting=existing)

    updated = runner._upsert_discovered_posting(
        db, _company(), _discovered(title="New Title", url="https://example.com/new")
    )

    assert updated.title == "New Title"
    assert updated.url == "https://example.com/new"
    assert updated.is_active is True
    assert updated.last_seen_at is not None


def test_existing_posting_with_a_description_keeps_it_on_re_discovery():
    """The core invariant this rewrite depends on: a posting whose
    description was already fetched (via api/routes/roadmaps.py's
    selection-time flow, not modeled here) must not have that description
    -- or its hash -- wiped back to None by a later discovery run just
    because DiscoveredPosting never carries one.
    """
    existing = JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-1",
        title="Software Engineer Intern",
        description="Full description fetched earlier",
        description_hash="some-hash",
    )
    db = _fake_db(existing_job_posting=existing)

    updated = runner._upsert_discovered_posting(db, _company(), _discovered(title="Updated Title"))

    assert updated.title == "Updated Title"
    assert updated.description == "Full description fetched earlier"
    assert updated.description_hash == "some-hash"


# ---------------------------------------------------------------------------
# _get_or_create_company_from_posting
# ---------------------------------------------------------------------------


def test_get_or_create_company_reuses_existing_row_by_name():
    existing = Company(id=uuid.uuid4(), name="Acme", ats_platform=runner.SOURCE_PLATFORM, ats_identifier="Acme")
    db = _fake_db(existing_job_posting=None)
    db.scalar.return_value = existing

    company = runner._get_or_create_company_from_posting(db, _discovered(company_name="Acme"))

    assert company is existing
    db.add.assert_not_called()


def test_get_or_create_company_creates_when_missing():
    db = MagicMock()
    db.scalar.return_value = None

    company = runner._get_or_create_company_from_posting(db, _discovered(company_name="New Co"))

    assert company.name == "New Co"
    assert company.ats_platform == runner.SOURCE_PLATFORM
    assert company.ats_identifier == "New Co"
    db.add.assert_called_once()
    db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# _filter_discovered_by_position
# ---------------------------------------------------------------------------


def test_filter_by_position_matches_case_insensitive_substring():
    postings = [
        _discovered(external_id="1", title="Software Engineer Intern"),
        _discovered(external_id="2", title="Product Designer Intern"),
        _discovered(external_id="3", title="SOFTWARE ENGINEER II"),
    ]

    matched = runner._filter_discovered_by_position(postings, "software engineer")

    assert {p.external_id for p in matched} == {"1", "3"}


def test_filter_by_position_empty_needle_returns_everything():
    postings = [_discovered(external_id="1"), _discovered(external_id="2")]
    assert runner._filter_discovered_by_position(postings, "   ") == postings


# ---------------------------------------------------------------------------
# _mark_stale_postings_inactive
# ---------------------------------------------------------------------------


def test_stale_postings_not_seen_this_run_are_marked_inactive():
    still_active = JobPosting(id=uuid.uuid4(), company_id=uuid.uuid4(), external_id="seen", title="A", is_active=True)
    gone = JobPosting(id=uuid.uuid4(), company_id=uuid.uuid4(), external_id="gone", title="B", is_active=True)

    db = MagicMock()
    db.scalars.return_value = iter([gone])  # query already filters to "not seen"

    runner._mark_stale_postings_inactive(db, seen_external_ids={"seen"})

    assert gone.is_active is False
    assert still_active.is_active is True  # untouched -- wasn't in the stale query result


# ---------------------------------------------------------------------------
# sync_job_posting_skills_batch -- shared with api/routes/roadmaps.py's
# selection-time extraction flow (_ensure_descriptions), which is why it's
# no longer prefixed with an underscore. Fail-open around
# extract_job_skills_batch: a whole-batch OpenAI failure is caught and
# logged rather than raised, so one bad batch can't crash the entire
# POST /roadmaps generation for postings whose extraction *did* succeed
# earlier in the request.
# ---------------------------------------------------------------------------


def _job_posting_needing_extraction() -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-1",
        title="Software Engineer",
        description="Requirements: Python",
        description_hash=None,
    )


def test_no_pending_postings_makes_no_openai_call(monkeypatch):
    called = False

    def fake_extract(descriptions):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(runner, "extract_job_skills_batch", fake_extract)

    db = MagicMock()
    runner.sync_job_posting_skills_batch(db, [], log_prefix="[test]")

    assert called is False


def test_pending_posting_with_no_description_is_stamped_without_a_call(monkeypatch):
    called = False

    def fake_extract(descriptions):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(runner, "extract_job_skills_batch", fake_extract)

    job_posting = JobPosting(
        id=uuid.uuid4(), company_id=uuid.uuid4(), external_id="ext-1", title="X", description=None
    )
    db = MagicMock()
    runner.sync_job_posting_skills_batch(db, [(job_posting, "some-hash")], log_prefix="[test]")

    assert called is False
    assert job_posting.description_hash == "some-hash"


def test_successful_extraction_stamps_hash(monkeypatch):
    from app.services.job_skill_extraction import ExtractedJobSkill, JobSkillExtractionResult

    job_posting = _job_posting_needing_extraction()
    new_hash = runner.hash_description(job_posting.description)

    monkeypatch.setattr(
        runner,
        "extract_job_skills_batch",
        lambda descriptions: [
            JobSkillExtractionResult(
                required_skills=[
                    ExtractedJobSkill(skill="Python", category="technical", evidence="...")
                ],
                preferred_skills=[],
            )
            for _ in descriptions
        ],
    )
    monkeypatch.setattr(
        runner, "get_or_create_skill", lambda db, name, category: MagicMock(id=uuid.uuid4())
    )

    db = MagicMock()
    db.scalars.return_value = iter([])  # no existing job_posting_skill rows

    runner.sync_job_posting_skills_batch(db, [(job_posting, new_hash)], log_prefix="[test]")

    assert job_posting.description_hash == new_hash


def test_openai_failure_is_caught_not_propagated(monkeypatch):
    """A whole-batch OpenAI failure (rate limit/timeout/auth) is caught
    and logged, not raised -- api/routes/roadmaps.py's
    _run_roadmap_generation_task must still be able to persist a roadmap
    from whatever descriptions it did get, rather than the entire
    generation failing because one posting's skill extraction hit a
    transient LLM error.
    """
    job_posting = _job_posting_needing_extraction()
    new_hash = runner.hash_description(job_posting.description)

    def failing_extract(descriptions):
        raise RuntimeError("simulated OpenAI outage")

    monkeypatch.setattr(runner, "extract_job_skills_batch", failing_extract)

    db = MagicMock()
    # Must not raise.
    runner.sync_job_posting_skills_batch(db, [(job_posting, new_hash)], log_prefix="[test]")

    assert job_posting.description_hash is None  # never stamped -- retried next time


def test_per_posting_skill_write_failure_does_not_block_other_postings(monkeypatch):
    """One posting's get_or_create_skill/db.execute failing (e.g. the
    documented Skill-name-uniqueness race) must not prevent a sibling
    posting in the same batch from getting its skills written and hash
    stamped.
    """
    from app.services.job_skill_extraction import ExtractedJobSkill, JobSkillExtractionResult

    failing_posting = _job_posting_needing_extraction()
    ok_posting = JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-2",
        title="Backend Engineer",
        description="Requirements: SQL",
        description_hash=None,
    )

    result = JobSkillExtractionResult(
        required_skills=[ExtractedJobSkill(skill="Python", category="technical", evidence="...")],
        preferred_skills=[],
    )
    monkeypatch.setattr(
        runner, "extract_job_skills_batch", lambda descriptions: [result, result]
    )

    # The first posting's job_posting_skill write fails (simulating e.g.
    # the documented Skill-name-uniqueness race); get_or_create_skill
    # itself succeeds for both so both postings reach the write step.
    monkeypatch.setattr(
        runner, "get_or_create_skill", lambda db, name, category: MagicMock(id=uuid.uuid4())
    )

    db = MagicMock()
    db.scalars.return_value = iter([])
    execute_calls = 0

    def flaky_execute(stmt):
        nonlocal execute_calls
        execute_calls += 1
        if execute_calls == 1:
            raise RuntimeError("simulated write failure for the first posting")
        return MagicMock()

    db.execute.side_effect = flaky_execute

    new_hash_failing = runner.hash_description(failing_posting.description)
    new_hash_ok = runner.hash_description(ok_posting.description)

    runner.sync_job_posting_skills_batch(
        db,
        [(failing_posting, new_hash_failing), (ok_posting, new_hash_ok)],
        log_prefix="[test]",
    )

    assert failing_posting.description_hash is None  # its write failed -- not stamped
    assert ok_posting.description_hash == new_hash_ok  # sibling posting unaffected
