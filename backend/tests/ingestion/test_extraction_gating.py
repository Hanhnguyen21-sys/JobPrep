"""Tests for Phase 1 items 3 (extract only for new/changed postings) and
the OpenAI-failure-isolation half of item 4, both in ingestion/runner.py.

Uses the existing description_hash column (models/job_posting.py) --
these tests confirm _upsert_job_posting's needs_extraction decision and
_sync_job_posting_skills_batch's failure handling, with a MagicMock `db`
(no real Postgres), same approach as tests/ingestion/test_company_sources.py.
"""

import uuid
from unittest.mock import MagicMock

from openai import OpenAIError

from app.ingestion import runner
from app.models.company import Company
from app.models.job_posting import JobPosting
from app.ingestion.common import NormalizedJobPosting


def _posting(**overrides) -> NormalizedJobPosting:
    defaults = dict(
        external_id="ext-1",
        title="Software Engineer",
        location="Remote",
        description="Requirements: Python",
        url="https://example.com/1",
        source_updated_at=None,
    )
    defaults.update(overrides)
    return NormalizedJobPosting(**defaults)


def _fake_db(existing_job_posting: JobPosting | None) -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = existing_job_posting
    return db


def _company() -> Company:
    return Company(id=uuid.uuid4(), name="Acme", ats_platform="greenhouse", ats_identifier="acme")


# ---------------------------------------------------------------------------
# _upsert_job_posting: new / unchanged / changed
# ---------------------------------------------------------------------------


def test_new_posting_needs_extraction():
    db = _fake_db(existing_job_posting=None)
    job_posting, needs_extraction, new_hash = runner._upsert_job_posting(
        db, _company(), _posting()
    )
    assert needs_extraction is True
    assert new_hash is not None


def test_existing_posting_unchanged_content_skips_extraction():
    description = "Requirements: Python"
    existing_hash = runner._hash_description(description)
    existing = JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-1",
        title="Software Engineer",
        description=description,
        description_hash=existing_hash,
    )
    db = _fake_db(existing_job_posting=existing)

    _, needs_extraction, new_hash = runner._upsert_job_posting(
        db, _company(), _posting(description=description)
    )

    assert needs_extraction is False
    assert new_hash == existing_hash


def test_existing_posting_changed_content_needs_extraction():
    old_hash = runner._hash_description("Requirements: Python")
    existing = JobPosting(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        external_id="ext-1",
        title="Software Engineer",
        description="Requirements: Python",
        description_hash=old_hash,
    )
    db = _fake_db(existing_job_posting=existing)

    _, needs_extraction, new_hash = runner._upsert_job_posting(
        db, _company(), _posting(description="Requirements: Python and Go")
    )

    assert needs_extraction is True
    assert new_hash != old_hash


# ---------------------------------------------------------------------------
# _sync_job_posting_skills_batch: extraction failure doesn't mark complete
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


def test_openai_failure_does_not_stamp_hash_and_returns_false(monkeypatch):
    job_posting = _job_posting_needing_extraction()
    new_hash = runner._hash_description(job_posting.description)

    def failing_extract(descriptions):
        raise OpenAIError("simulated OpenAI outage")

    monkeypatch.setattr(runner, "extract_job_skills_batch", failing_extract)

    db = MagicMock()
    succeeded = runner._sync_job_posting_skills_batch(
        db, [(job_posting, new_hash)], log_prefix="[test]"
    )

    assert succeeded is False
    assert job_posting.description_hash is None  # never marked complete


def test_openai_failure_does_not_raise(monkeypatch):
    """The caller (_ingest_company_for_position) must not see this as an
    exception -- an OpenAI failure only skips extraction, it must not
    also discard the job postings already upserted this run.
    """
    job_posting = _job_posting_needing_extraction()
    new_hash = runner._hash_description(job_posting.description)

    monkeypatch.setattr(
        runner,
        "extract_job_skills_batch",
        lambda descriptions: (_ for _ in ()).throw(OpenAIError("boom")),
    )

    db = MagicMock()
    # Should not raise.
    runner._sync_job_posting_skills_batch(db, [(job_posting, new_hash)], log_prefix="[test]")


def test_successful_extraction_stamps_hash_and_returns_true(monkeypatch):
    from app.services.job_skill_extraction import ExtractedJobSkill, JobSkillExtractionResult

    job_posting = _job_posting_needing_extraction()
    new_hash = runner._hash_description(job_posting.description)

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
    from types import SimpleNamespace

    def fake_execute(stmt):
        # _bulk_resolve_skills' bulk INSERT ... RETURNING for the new
        # "Python" skill -- everything else (the existing job_posting_skill
        # lookup, the final job_posting_skill upsert) can return empty/a
        # plain mock, this test only cares that skill resolution works
        # without a real DB.
        text = str(stmt)
        if "INSERT" in text and "RETURNING" in text and "skills" in text:
            return [SimpleNamespace(id=uuid.uuid4(), name="Python", category="technical")]
        return iter([])

    db = MagicMock()
    db.scalars.return_value = iter([])  # no existing Skill/job_posting_skill rows
    db.execute.side_effect = fake_execute

    succeeded = runner._sync_job_posting_skills_batch(
        db, [(job_posting, new_hash)], log_prefix="[test]"
    )

    assert succeeded is True
    assert job_posting.description_hash == new_hash


def test_no_pending_postings_returns_true_without_openai_call(monkeypatch):
    called = False

    def fake_extract(descriptions):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(runner, "extract_job_skills_batch", fake_extract)

    db = MagicMock()
    result = runner._sync_job_posting_skills_batch(db, [], log_prefix="[test]")

    assert result is True
    assert called is False
