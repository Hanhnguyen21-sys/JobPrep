

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.ingestion import readme as readme_source
from app.ingestion.readme import DiscoveredPosting
from app.models.company import Company
from app.models.job_posting import JobPosting, job_posting_skill
from app.models.search_cache import JobSearchCache
from app.repositories.skills import get_or_create_skill
from app.ingestion.query_normalization import cache_key, title_matches_query
from app.services.job_skill_extraction import (
    ExtractedJobSkill,
    JobSkillExtractionResult,
    extract_job_skills_batch,
)

SOURCE_PLATFORM = "readme"


def run_ingestion(discovered_postings: list[DiscoveredPosting] | None = None) -> None:
   
    db = SessionLocal()
    try:
        discovered = (
            discovered_postings
            if discovered_postings is not None
            else readme_source.discover_postings()
        )
        print(f"[ingestion] readme: discovered {len(discovered)} posting(s)")

        job_postings = _sync_discovered_postings(db, discovered)
        _mark_stale_postings_inactive(db, {jp.external_id for jp in job_postings})

        db.commit()
        print(f"[ingestion] readme: ok -- {len(job_postings)} synced")
    except Exception as exc:  # a bad fetch/parse shouldn't leave a half-written run committed
        db.rollback()
        print(f"[ingestion] readme: FAILED -- {exc}")
    finally:
        db.close()


def run_targeted_ingestion(
    db: Session,
    desired_position: str,
    freshness_minutes: int = 60,
    stats: dict | None = None,
    discovered_postings: list[DiscoveredPosting] | None = None,
) -> list[JobPosting]:
    key = cache_key(desired_position)

    if freshness_minutes > 0:
        cached = _get_cached_matches(db, key, desired_position, freshness_minutes)
        if cached is not None:
            print(f"[jobs] cache hit for {desired_position!r} ({len(cached)} posting(s))")
            if stats is not None:
                stats.update(attempted=0, succeeded=0, failed=0)
            return cached

    matched: list[JobPosting] = []
    succeeded = 0
    failed = 0
    try:
        discovered = (
            discovered_postings
            if discovered_postings is not None
            else readme_source.discover_postings()
        )
        filtered = _filter_discovered_by_position(discovered, desired_position)
        print(
            f"[jobs] readme: {len(filtered)}/{len(discovered)} posting(s) "
            f"match {desired_position!r}"
        )

        matched = _sync_discovered_postings(db, filtered)
        db.commit()
        succeeded = 1
    except Exception as exc:
        db.rollback()
        failed = 1
        print(f"[jobs] readme: FAILED -- {exc}")

    if stats is not None:
        stats.update(attempted=1, succeeded=succeeded, failed=failed)

    _mark_position_ingested(db, key)
    db.commit()
    return matched


def _sync_discovered_postings(
    db: Session, postings: list[DiscoveredPosting]
) -> list[JobPosting]:
    """Resolves/creates each posting's Company and upserts its
    JobPosting row. Shared by both entry points above.
    """
    return [
        _upsert_discovered_posting(db, _get_or_create_company_from_posting(db, posting), posting)
        for posting in postings
    ]


def _filter_discovered_by_position(
    postings: list[DiscoveredPosting], desired_position: str
) -> list[DiscoveredPosting]:
    """Broad token-based match against posting title (see
    query_normalization.title_matches_query) -- handles near-miss
    phrasing a raw substring check can't (e.g. "Software Engineer Intern"
    matching a posting titled "Software Engineering Internship" or "SWE
    Intern"). Still simple/explainable on purpose -- a small,
    hand-maintained synonym table, not embeddings/semantic similarity.
    """
    if not desired_position.strip():
        return postings
    return [p for p in postings if title_matches_query(desired_position, p.title)]


def _get_or_create_company_from_posting(db: Session, posting: DiscoveredPosting) -> Company:
    existing = db.scalar(
        select(Company).where(
            Company.ats_platform == SOURCE_PLATFORM,
            Company.ats_identifier == posting.company_name,
        )
    )
    if existing is not None:
        return existing

    company = Company(
        name=posting.company_name,
        ats_platform=SOURCE_PLATFORM,
        ats_identifier=posting.company_name,
    )
    db.add(company)
    db.flush()  # assigns company.id without committing yet
    return company


def _upsert_discovered_posting(
    db: Session, company: Company, posting: DiscoveredPosting
) -> JobPosting:
    """Upserts metadata-only fields (title/url/source_updated_at/
    last_seen_at/is_active). Deliberately never touches `description`/
    `description_hash` -- discovery never has a description (see
    ingestion/readme.py's module docstring), and a selected posting's
    description (fetched later, see api/routes/roadmaps.py) must survive
    every later discovery re-run rather than get wiped back to None by it.
    """
    existing = db.scalar(
        select(JobPosting).where(
            JobPosting.company_id == company.id,
            JobPosting.external_id == posting.external_id,
        )
    )

    if existing is None:
        job_posting = JobPosting(
            company_id=company.id,
            external_id=posting.external_id,
            title=posting.title,
            url=posting.url,
            source_updated_at=posting.source_updated_at,
        )
        db.add(job_posting)
        db.flush()  # assigns job_posting.id without committing yet
        return job_posting

    existing.title = posting.title
    existing.url = posting.url
    existing.source_updated_at = posting.source_updated_at
    existing.last_seen_at = datetime.now(timezone.utc)
    existing.is_active = True
    return existing


def _mark_stale_postings_inactive(db: Session, seen_external_ids: set[str]) -> None:
    """Any README-sourced posting not seen in this run's discovery output
    is marked inactive (not deleted, to preserve history/roadmap links).
    Applied across every README-sourced company at once, not per company
    -- discover_postings() already returns the full current picture for
    this source in one call, unlike the old per-company Greenhouse/Lever
    boards.
    """
    stale = db.scalars(
        select(JobPosting)
        .join(Company, Company.id == JobPosting.company_id)
        .where(
            Company.ats_platform == SOURCE_PLATFORM,
            JobPosting.is_active.is_(True),
            JobPosting.external_id.notin_(seen_external_ids),
        )
    )
    for job_posting in stale:
        job_posting.is_active = False


def _get_cached_matches(
    db: Session, key: str, desired_position: str, freshness_minutes: int
) -> list[JobPosting] | None:

    cache_row = db.scalar(
        select(JobSearchCache).where(JobSearchCache.target_position == key)
    )
    if cache_row is None:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=freshness_minutes)
    if cache_row.last_ingested_at < cutoff:
        return None  # stale -- caller falls through to a live pull

    # Broad token-based match, not a raw ILIKE -- see
    # query_normalization.title_matches_query and _filter_discovered_by_
    # position above for why (near-miss phrasing like "SWE Intern" /
    # "Software Engineering Internship" needs more than substring
    # containment).
    candidates = db.scalars(
        select(JobPosting).where(JobPosting.is_active.is_(True))
    )
    return [jp for jp in candidates if title_matches_query(desired_position, jp.title)]


def _mark_position_ingested(db: Session, key: str) -> None:
    """Upsert job_search_cache so the next search for this exact
    normalized position within freshness_minutes hits the cache.
    """
    stmt = pg_insert(JobSearchCache.__table__).values(
        target_position=key,
        last_ingested_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[JobSearchCache.__table__.c.target_position],
        set_={"last_ingested_at": stmt.excluded.last_ingested_at},
    )
    db.execute(stmt)


def hash_description(description: str | None) -> str | None:
    if not description:
        return None
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def sync_job_posting_skills_batch(
    db: Session,
    pending: list[tuple[JobPosting, str | None]],
    log_prefix: str,
) -> None:
    if not pending:
        return

    to_extract = [(jp, new_hash) for jp, new_hash in pending if jp.description]
    for job_posting, new_hash in pending:
        if not job_posting.description:
            job_posting.description_hash = new_hash

    if not to_extract:
        return

    print(f"{log_prefix}   extracting skills: batch of {len(to_extract)} posting(s)")

    try:
        results = extract_job_skills_batch([jp.description for jp, _ in to_extract])
    except Exception as exc:
        # LLM call failed entirely for this batch (rate limit/timeout/auth) --
        # skip skill extraction for all of them rather than failing the
        # whole roadmap request; descriptions themselves are still saved.
        print(f"{log_prefix}   skill extraction failed for batch: {exc}")
        return

    for (job_posting, new_hash), result in zip(to_extract, results):
        try:
            _apply_job_skill_extraction(db, job_posting, new_hash, result)
        except Exception as exc:
            # One posting's skill-write failed (e.g. get_or_create_skill's
            # known TOCTOU race) -- skip just this posting, not the batch.
            print(f"{log_prefix}   skill write failed for posting {job_posting.id}: {exc}")

def _apply_job_skill_extraction(
    db: Session,
    job_posting: JobPosting,
    new_hash: str | None,
    result: JobSkillExtractionResult,
) -> None:
    by_name: dict[str, tuple[str, ExtractedJobSkill]] = {}
    for item in result.required_skills:
        by_name.setdefault(item.skill.strip().lower(), ("required", item))
    for item in result.preferred_skills:
        by_name.setdefault(item.skill.strip().lower(), ("preferred", item))

    resolved = [
        (get_or_create_skill(db, item.skill, item.category), requirement_level, item)
        for requirement_level, item in by_name.values()
    ]

    new_skill_ids = {skill.id for skill, _, _ in resolved}

    existing_skill_ids = set(
        db.scalars(
            select(job_posting_skill.c.skill_id).where(
                job_posting_skill.c.job_posting_id == job_posting.id
            )
        )
    )
    stale_skill_ids = existing_skill_ids - new_skill_ids
    if stale_skill_ids:
        db.execute(
            delete(job_posting_skill).where(
                job_posting_skill.c.job_posting_id == job_posting.id,
                job_posting_skill.c.skill_id.in_(stale_skill_ids),
            )
        )

    for skill, requirement_level, item in resolved:
        stmt = pg_insert(job_posting_skill).values(
            job_posting_id=job_posting.id,
            skill_id=skill.id,
            requirement_level=requirement_level,
            evidence=item.evidence,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[job_posting_skill.c.job_posting_id, job_posting_skill.c.skill_id],
            set_={
                "requirement_level": stmt.excluded.requirement_level,
                "evidence": stmt.excluded.evidence,
            },
        )
        db.execute(stmt)

    job_posting.description_hash = new_hash


if __name__ == "__main__":
    # Manual trigger: `python -m app.ingestion.runner` from backend/, venv
    # active.
    run_ingestion()
