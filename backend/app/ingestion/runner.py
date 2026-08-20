"""Ingestion path 1: pull a handful of companies from the Greenhouse and
Lever public APIs and sync them into `Company` / `JobPosting` /
`job_posting_skill`.

Runs as a standalone script (see the manual trigger below), not a FastAPI
request, so it opens and closes its own DB session directly via
SessionLocal rather than the `get_db()` dependency generator in
db/session.py, which only exists to be wired into FastAPI's Depends().

Cost/time control: re-fetching every company's postings on every run is
cheap, but re-running AI skill extraction on every posting every run is
not -- a board like GitLab's has 100+ open postings, and each extraction
is an OpenAI call. Three things keep this sane:

1. Each JobPosting stores a `description_hash` (sha256 of its description
   text). A posting only gets (re-)extracted when that hash doesn't match
   what's stored -- i.e. it's brand new, or its content actually changed
   since we last saw it. Hashing the text itself (rather than trusting
   either ATS's own timestamp) is deliberate -- Lever's `createdAt` (see
   ingestion/lever.py) reflects creation, not last edit, so it can't be
   trusted to signal "this posting changed."

2. `extraction_limit_per_company` caps how many postings get extracted
   per company per run, so a first run against a big board doesn't sit
   silently making a huge number of sequential API calls. Postings past
   the limit are left with a stale/missing description_hash on purpose --
   NOT updated at upsert time -- so the next run's hash comparison still
   sees them as needing extraction instead of silently skipping them
   forever. Progress prints as it goes, so a long run doesn't look hung.

3. Postings that survive both filters are extracted in batches, not one
   OpenAI call each: `services/job_skill_extraction.extract_job_skills_batch`
   groups up to BATCH_SIZE (5) descriptions into a single prompt/response,
   so e.g. 5 postings needing extraction cost 1 call instead of 5. See
   `_sync_job_posting_skills_batch` below.

Postings that disappear from a company's board between runs are marked
`is_active = False` rather than deleted, so any match/roadmap history
tied to them isn't silently lost.

Two entry points:
- run_ingestion() -- the broad, standalone-script path above: pulls
  everything from DEFAULT_COMPANIES, keeps job_postings generally
  populated, marks postings that vanished as inactive.
- run_targeted_ingestion() -- the on-demand, per-user path: filters to
  postings matching a desired position *before* saving/extracting
  anything, called from api/routes/jobs.py with the request's own DB
  session. Never touches is_active -- see its docstring for why.

Caching (run_targeted_ingestion only): the live fetch+extract pipeline is
the slow part of a job match request (sequential ATS calls + sequential
OpenAI extraction), and it's entirely determined by `desired_position` --
not by which user or resume triggered it. So `job_search_cache` tracks the
last time a given normalized position was fully ingested; a repeat search
for the same position within `freshness_minutes` skips straight to
querying already-ingested job_postings (see _get_cached_matches) instead
of re-hitting Greenhouse/Lever and re-running extraction. This is a plain
table, not inferred from job_postings.last_seen_at, because "zero postings
currently match" is ambiguous between "genuinely zero" and "never
searched" -- a dedicated timestamp resolves that.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.ingestion import greenhouse, lever
from app.ingestion.common import NormalizedJobPosting
from app.models.company import Company
from app.models.job_posting import JobPosting, job_posting_skill
from app.models.search_cache import JobSearchCache
from app.repositories.skills import get_or_create_skill
from app.services.job_skill_extraction import (
    ExtractedJobSkill,
    JobSkillExtractionResult,
    extract_job_skills_batch,
)


@dataclass(frozen=True)
class CompanySource:
    name: str
    ats_platform: Literal["greenhouse", "lever"]
    ats_identifier: str


# Verified live at write time: gitlab/coinbase are real, active Greenhouse
# boards; leverdemo is Lever's own public demo board (safer as a default
# than a real company's Lever slug, which could break silently if they
# ever switch ATS providers).
DEFAULT_COMPANIES: list[CompanySource] = [
    CompanySource(name="GitLab", ats_platform="greenhouse", ats_identifier="gitlab"),
    CompanySource(name="Coinbase", ats_platform="greenhouse", ats_identifier="coinbase"),
    CompanySource(name="Lever (demo board)", ats_platform="lever", ats_identifier="leverdemo"),
]

FETCHERS: dict[str, Callable[[str], list[NormalizedJobPosting]]] = {
    "greenhouse": greenhouse.fetch_jobs,
    "lever": lever.fetch_jobs,
}


def run_ingestion(
    companies: list[CompanySource] | None = None,
    extraction_limit_per_company: int | None = 5,
    fetch_limit_per_company: int | None = None,
) -> None:
    """Entry point: ingest every company in `companies` (defaults to
    DEFAULT_COMPANIES). Each company commits independently, so one
    company's failure (bad token, ATS downtime) doesn't roll back
    everything ingested before it.

    `extraction_limit_per_company` defaults to a small number so a fresh
    run against a big board (GitLab et al.) finishes in a reasonable time
    instead of making 100+ sequential OpenAI calls. Pass None for no cap
    once you're confident the pipeline works end to end -- re-running
    with a higher/no limit will pick up exactly the postings skipped by
    earlier runs, not redo already-extracted ones.

    `fetch_limit_per_company` is a separate, coarser knob: it truncates
    the postings list right after fetching, before anything is upserted
    or extracted -- useful for quick local iteration (e.g. "only touch 10
    postings total this run") without waiting on a full board fetch's
    worth of DB writes. It's independent of extraction_limit_per_company,
    so set both if you want every fetched posting to actually get
    extracted (e.g. fetch_limit_per_company=10,
    extraction_limit_per_company=10 or None).
    """
    companies = companies if companies is not None else DEFAULT_COMPANIES
    db = SessionLocal()
    try:
        for source in companies:
            try:
                _ingest_company(
                    db, source, extraction_limit_per_company, fetch_limit_per_company
                )
                db.commit()
            except Exception as exc:  # one bad company shouldn't stop the run
                db.rollback()
                print(f"[ingestion] {source.name}: FAILED -- {exc}")
    finally:
        db.close()


def _ingest_company(
    db: Session,
    source: CompanySource,
    extraction_limit: int | None,
    fetch_limit: int | None,
) -> None:
    fetch = FETCHERS[source.ats_platform]
    postings = fetch(source.ats_identifier)
    if fetch_limit is not None:
        postings = postings[:fetch_limit]
    print(f"[ingestion] {source.name}: fetched {len(postings)} posting(s)")

    company = _get_or_create_company(db, source)

    seen_external_ids: set[str] = set()
    pending: list[tuple[JobPosting, str | None]] = []
    needs_extraction_count = 0

    for posting in postings:
        seen_external_ids.add(posting.external_id)
        job_posting, needs_extraction, new_hash = _upsert_job_posting(db, company, posting)

        if not needs_extraction:
            continue
        needs_extraction_count += 1

        if extraction_limit is not None and len(pending) >= extraction_limit:
            continue  # left with a stale/missing hash -- picked up again next run

        pending.append((job_posting, new_hash))

    _sync_job_posting_skills_batch(db, pending, log_prefix="[ingestion]")

    skipped = needs_extraction_count - len(pending)
    print(
        f"[ingestion] {source.name}: ok -- {len(pending)} extracted"
        + (f", {skipped} skipped (limit reached, will retry next run)" if skipped else "")
    )

    # Postings that used to exist for this company but weren't in this
    # fetch anymore -- mark inactive rather than delete, to preserve history.
    stale = db.scalars(
        select(JobPosting).where(
            JobPosting.company_id == company.id,
            JobPosting.is_active.is_(True),
            JobPosting.external_id.notin_(seen_external_ids),
        )
    )
    for job_posting in stale:
        job_posting.is_active = False


def run_targeted_ingestion(
    db: Session,
    desired_position: str,
    companies: list[CompanySource] | None = None,
    extraction_limit_per_company: int | None = 10,
    freshness_minutes: int = 60,
) -> list[JobPosting]:
    """On-demand counterpart to run_ingestion(): fetches the same
    DEFAULT_COMPANIES but filters to postings whose title matches
    `desired_position` *before* saving or extracting anything, and
    returns the matched JobPosting rows directly for the caller to use
    (see api/routes/jobs.py).

    Takes an existing `db` Session rather than opening its own -- this is
    meant to be called from inside a FastAPI request (via Depends(get_db)),
    not as a standalone script, so the caller's request lifecycle owns the
    session, not this function.

    Deliberately does NOT run run_ingestion()/_ingest_company()'s
    "mark postings inactive if they disappeared" step. That logic assumes
    it saw a company's *entire* current board; here we only ever see a
    filtered subset, so treating "not in this subset" as "gone" would
    incorrectly deactivate postings that are still live and just didn't
    match this particular search.

    `freshness_minutes` controls the job_search_cache check (see module
    docstring): if this exact normalized position was fully ingested more
    recently than this, skip the live fetch+extract pipeline entirely and
    return already-ingested matches straight from job_postings. Pass 0 to
    always force a live pull.
    """
    normalized_position = desired_position.strip().lower()

    if freshness_minutes > 0:
        cached = _get_cached_matches(db, normalized_position, freshness_minutes)
        if cached is not None:
            print(f"[jobs] cache hit for {desired_position!r} ({len(cached)} posting(s))")
            return cached

    companies = companies if companies is not None else DEFAULT_COMPANIES
    matched: list[JobPosting] = []
    for source in companies:
        try:
            matched.extend(
                _ingest_company_for_position(
                    db, source, desired_position, extraction_limit_per_company
                )
            )
            db.commit()  # per company, same isolation reasoning as run_ingestion()
        except Exception as exc:
            db.rollback()
            print(f"[jobs] {source.name}: FAILED -- {exc}")

    _mark_position_ingested(db, normalized_position)
    db.commit()
    return matched


def _get_cached_matches(
    db: Session, normalized_position: str, freshness_minutes: int
) -> list[JobPosting] | None:
    """Returns already-ingested matches if `normalized_position` was fully
    ingested within `freshness_minutes`, else None (meaning: no fresh
    cache entry, caller should run the live pipeline).
    """
    cache_row = db.scalar(
        select(JobSearchCache).where(JobSearchCache.target_position == normalized_position)
    )
    if cache_row is None:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=freshness_minutes)
    if cache_row.last_ingested_at < cutoff:
        return None  # stale -- caller falls through to a live pull

    return list(
        db.scalars(
            select(JobPosting).where(
                JobPosting.title.ilike(f"%{normalized_position}%"),
                JobPosting.is_active.is_(True),
            )
        )
    )


def _mark_position_ingested(db: Session, normalized_position: str) -> None:
    """Upsert job_search_cache so the next search for this exact
    normalized position within freshness_minutes hits the cache.
    """
    stmt = pg_insert(JobSearchCache.__table__).values(
        target_position=normalized_position,
        last_ingested_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[JobSearchCache.__table__.c.target_position],
        set_={"last_ingested_at": stmt.excluded.last_ingested_at},
    )
    db.execute(stmt)


def _ingest_company_for_position(
    db: Session,
    source: CompanySource,
    desired_position: str,
    extraction_limit: int | None,
) -> list[JobPosting]:
    fetch = FETCHERS[source.ats_platform]
    postings = fetch(source.ats_identifier)
    matched = _filter_postings_by_position(postings, desired_position)
    print(
        f"[jobs] {source.name}: {len(matched)}/{len(postings)} posting(s) "
        f"match {desired_position!r}"
    )

    company = _get_or_create_company(db, source)

    results: list[JobPosting] = []
    pending: list[tuple[JobPosting, str | None]] = []
    for posting in matched:
        job_posting, needs_extraction, new_hash = _upsert_job_posting(db, company, posting)
        if needs_extraction and (extraction_limit is None or len(pending) < extraction_limit):
            pending.append((job_posting, new_hash))
        results.append(job_posting)

    _sync_job_posting_skills_batch(db, pending, log_prefix="[jobs]")

    return results


def _filter_postings_by_position(
    postings: list[NormalizedJobPosting], desired_position: str
) -> list[NormalizedJobPosting]:
    """Case-insensitive substring match against posting title. Simple on
    purpose -- matching by extracted skills or semantic/embedding
    similarity is services/matching.py's job, later, not this.
    """
    needle = desired_position.strip().lower()
    if not needle:
        return postings
    return [p for p in postings if needle in p.title.lower()]


def _get_or_create_company(db: Session, source: CompanySource) -> Company:
    existing = db.scalar(
        select(Company).where(
            Company.ats_platform == source.ats_platform,
            Company.ats_identifier == source.ats_identifier,
        )
    )
    if existing is not None:
        existing.name = source.name
        return existing

    company = Company(
        name=source.name,
        ats_platform=source.ats_platform,
        ats_identifier=source.ats_identifier,
    )
    db.add(company)
    db.flush()  # assigns company.id without committing yet
    return company


def _hash_description(description: str | None) -> str | None:
    if not description:
        return None
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def _upsert_job_posting(
    db: Session, company: Company, posting: NormalizedJobPosting
) -> tuple[JobPosting, bool, str | None]:
    """Returns (job_posting, needs_extraction, new_hash).

    `needs_extraction` is True for brand-new postings and for existing
    ones whose content hash no longer matches. Deliberately does NOT
    write `description_hash` onto the row -- that only happens once
    _sync_job_posting_skills() actually runs (see module docstring) --
    so a posting skipped this run due to extraction_limit is still
    correctly flagged as needing extraction on the next run.
    """
    new_hash = _hash_description(posting.description)

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
            location=posting.location,
            description=posting.description,
            url=posting.url,
            source_updated_at=posting.source_updated_at,
        )
        db.add(job_posting)
        db.flush()  # assigns job_posting.id without committing yet
        return job_posting, True, new_hash

    needs_extraction = new_hash != existing.description_hash
    existing.title = posting.title
    existing.location = posting.location
    existing.description = posting.description
    existing.url = posting.url
    existing.source_updated_at = posting.source_updated_at
    existing.last_seen_at = datetime.now(timezone.utc)
    existing.is_active = True
    return existing, needs_extraction, new_hash


def _sync_job_posting_skills_batch(
    db: Session,
    pending: list[tuple[JobPosting, str | None]],
    log_prefix: str,
) -> None:
    """Batch counterpart to the old one-OpenAI-call-per-posting flow:
    extracts skills for every (job_posting, new_hash) pair in `pending`
    using as few OpenAI calls as possible
    (see services/job_skill_extraction.extract_job_skills_batch, which
    internally chunks into groups of BATCH_SIZE), then applies each
    posting's result and stamps description_hash -- same "only stamped
    once extraction actually completes" rule as before, so a posting
    left out of `pending` by the caller's extraction_limit is still
    correctly flagged as needing extraction on the next run.
    """
    if not pending:
        return

    # No description at all -- nothing to send to the model, same
    # short-circuit the old per-posting path had.
    to_extract = [(jp, new_hash) for jp, new_hash in pending if jp.description]
    for job_posting, new_hash in pending:
        if not job_posting.description:
            job_posting.description_hash = new_hash

    if not to_extract:
        return

    print(f"{log_prefix}   extracting skills: batch of {len(to_extract)} posting(s)")
    results = extract_job_skills_batch([jp.description for jp, _ in to_extract])

    for (job_posting, new_hash), result in zip(to_extract, results):
        _apply_job_skill_extraction(db, job_posting, new_hash, result)


def _apply_job_skill_extraction(
    db: Session,
    job_posting: JobPosting,
    new_hash: str | None,
    result: JobSkillExtractionResult,
) -> None:
    """Writes one posting's extraction result to job_posting_skill rows
    and stamps description_hash. Split out from
    _sync_job_posting_skills_batch so "how the result was obtained"
    (batched now) stays separate from "what to do with one posting's
    result" (unchanged from before batching).
    """
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
    # active. scheduler/refresh_ats.py (later) will call run_ingestion()
    # the same way, just on a schedule instead of by hand.
    run_ingestion()
