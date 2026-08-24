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
  everything from the tracked companies in the `companies` table (see
  _get_tracked_companies), keeps job_postings generally populated, marks
  postings that vanished as inactive.
- run_targeted_ingestion() -- the on-demand, per-user path: filters to
  postings matching a desired position *before* saving/extracting
  anything, called from api/routes/jobs.py with the request's own DB
  session. Never touches is_active -- see its docstring for why.

Company source of truth: both entry points read the companies to ingest
from the `companies` table (_get_tracked_companies), not from a hardcoded
list. A company row needs both `ats_platform` and `ats_identifier` set to
be picked up -- see db/sql/12_seed_verified_greenhouse_sources.sql for how
new sources get added. Callers can still pass an explicit `companies=`
override (used by tests) to bypass the DB read entirely.

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

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

import httpx
from openai import OpenAIError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import tuple_

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion import greenhouse, lever
from app.ingestion.common import NormalizedJobPosting
from app.ingestion.query_normalization import cache_key, normalize_query
from app.models.company import Company
from app.models.job_posting import JobPosting, job_posting_skill
from app.models.search_cache import JobSearchCache
from app.models.skill import Skill
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


FETCHERS: dict[str, Callable[[str], list[NormalizedJobPosting]]] = {
    "greenhouse": greenhouse.fetch_jobs,
    "lever": lever.fetch_jobs,
}

# Title-filtered counterpart to FETCHERS -- see greenhouse.py's
# fetch_jobs_filtered docstring. Used by the targeted/on-demand path
# (_ingest_company_for_position) instead of FETCHERS + a post-hoc filter,
# so a big board's non-matching postings never get their HTML-stripped/
# constructed in the first place.
FETCHERS_FILTERED: dict[str, Callable[[str, Callable[[str], bool]], list[NormalizedJobPosting]]] = {
    "greenhouse": greenhouse.fetch_jobs_filtered,
    "lever": lever.fetch_jobs_filtered,
}

# Async counterpart to FETCHERS_FILTERED -- used by
# _fetch_sources_concurrently_async to fetch every tracked company's
# board at once (bounded concurrency) instead of one company at a time.
FETCHERS_FILTERED_ASYNC = {
    "greenhouse": greenhouse.fetch_jobs_filtered_async,
    "lever": lever.fetch_jobs_filtered_async,
}

# ATS/network-shaped failures that are safe to isolate to one company
# without aborting the rest of the search -- httpx.HTTPError covers both
# connection/timeout failures and non-2xx responses; KeyError/ValueError
# cover a malformed/unexpected ATS payload (a missing "title" field, an
# unparseable date). Deliberately NOT a bare `except Exception`: a real
# programming error or a genuine database issue should fail loudly, not
# be silently swallowed per-company (see run_ingestion()/
# run_targeted_ingestion()'s use of this).
COMPANY_ISOLATABLE_ERRORS = (httpx.HTTPError, KeyError, ValueError)


def _get_tracked_companies(db: Session) -> list[Company]:
    """Company rows with a usable ATS source -- the runtime registry both
    entry points default to when no explicit `companies=` override is
    given. Ordered by name for a deterministic ingestion order run to run.

    Excludes any company missing `ats_platform` and/or `ats_identifier`
    (e.g. a future career-page-only row with nothing to fetch from yet).
    Add a new tracked company by inserting a row into `companies` --
    see db/sql/12_seed_verified_greenhouse_sources.sql -- not by editing
    this module.
    """
    return list(
        db.scalars(
            select(Company)
            .where(Company.ats_platform.isnot(None), Company.ats_identifier.isnot(None))
            .order_by(Company.name)
        )
    )


def _as_company_sources(companies: list[Company]) -> list[CompanySource]:
    """Adapts DB `Company` rows into the `CompanySource` shape the
    per-company ingestion helpers (_ingest_company, _ingest_company_for_
    position) already expect -- keeps this a runtime-registry change only,
    not a rework of how a company gets fetched/upserted.
    """
    return [
        CompanySource(name=c.name, ats_platform=c.ats_platform, ats_identifier=c.ats_identifier)
        for c in companies
    ]


def run_ingestion(
    companies: list[CompanySource] | None = None,
    extraction_limit_per_company: int | None = 5,
    fetch_limit_per_company: int | None = None,
) -> None:
    """Entry point: ingest every company in `companies` (defaults to the
    tracked companies in the `companies` table -- see
    _get_tracked_companies). Each company commits independently, so one
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
    db = SessionLocal()
    try:
        sources = (
            companies if companies is not None else _as_company_sources(_get_tracked_companies(db))
        )
        if not sources:
            print("[ingestion] no tracked companies in the database -- nothing to ingest")
            return

        for source in sources:
            try:
                _ingest_company(
                    db, source, extraction_limit_per_company, fetch_limit_per_company
                )
                db.commit()
            except COMPANY_ISOLATABLE_ERRORS as exc:
                # ATS/data-shape failure for one company shouldn't stop
                # the run -- a real programming/DB error is NOT caught
                # here (see COMPANY_ISOLATABLE_ERRORS) and will surface.
                db.rollback()
                print(f"[ingestion] {source.name}: FAILED ({type(exc).__name__}) -- {exc}")
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
    stats: dict | None = None,
) -> list[JobPosting]:
    """On-demand counterpart to run_ingestion(): fetches the same tracked
    companies (see _get_tracked_companies) but filters to postings whose
    title matches `desired_position` *before* saving or extracting
    anything, and returns the matched JobPosting rows directly for the
    caller to use (see api/routes/jobs.py).

    If no tracked companies exist in the database (and no explicit
    `companies=` override was given), this returns an empty list without
    making any Greenhouse/Lever/OpenAI call and without marking
    `desired_position` as ingested -- there's nothing to retry sooner for,
    and nothing was actually processed.

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

    Fetch step runs concurrently across companies (bounded by
    settings.ats_max_concurrency -- see _fetch_sources_concurrently),
    *then* every DB write happens afterward, sequentially, on this one
    Session -- a plain sync SQLAlchemy Session is not thread/task-safe to
    share across concurrent requests, so it is never touched until all
    the concurrent I/O has finished.

    `stats`, if given, gets `attempted`/`succeeded`/`failed` company
    counts written into it (int values) -- used by api/routes/jobs.py's
    background refresh task to decide 'completed' vs 'partial_failure'
    vs 'failed' for a JobSearchTask. None (default) means no tracking,
    same behavior as before this parameter existed.
    """
    key = cache_key(desired_position)

    if freshness_minutes > 0:
        cached = _get_cached_matches(db, key, freshness_minutes)
        if cached is not None:
            print(f"[jobs] cache hit for {desired_position!r} ({len(cached)} posting(s))")
            return cached

    sources = companies if companies is not None else _as_company_sources(_get_tracked_companies(db))
    if not sources:
        print("[jobs] no tracked companies in the database -- skipping live ingestion")
        return []

    fetch_results = _fetch_sources_concurrently(
        sources, desired_position, get_settings().ats_max_concurrency
    )

    matched: list[JobPosting] = []
    any_company_succeeded = False
    for result in fetch_results:
        if stats is not None:
            stats["attempted"] = stats.get("attempted", 0) + 1
        if result.error is not None:
            if stats is not None:
                stats["failed"] = stats.get("failed", 0) + 1
            print(f"[jobs] {result.source.name}: FAILED ({type(result.error).__name__}) -- {result.error}")
            continue
        try:
            matched.extend(
                _persist_company_postings(
                    db, result.source, result.postings, extraction_limit_per_company
                )
            )
            db.commit()  # per company, same isolation reasoning as run_ingestion()
            any_company_succeeded = True
            if stats is not None:
                stats["succeeded"] = stats.get("succeeded", 0) + 1
        except COMPANY_ISOLATABLE_ERRORS as exc:
            # A DB/data-shape failure for one company shouldn't discard
            # matches already found from healthy companies -- a real
            # programming/DB-integrity error is NOT caught here (see
            # COMPANY_ISOLATABLE_ERRORS) and will surface as a 500.
            db.rollback()
            if stats is not None:
                stats["failed"] = stats.get("failed", 0) + 1
            print(f"[jobs] {result.source.name}: FAILED ({type(exc).__name__}) -- {exc}")

    if any_company_succeeded:
        _mark_position_ingested(db, key)
        db.commit()
    else:
        # Every company failed -- nothing was actually ingested, so don't
        # claim this position is fresh; the next search should retry
        # immediately rather than trusting an empty cache entry for
        # freshness_minutes.
        print(f"[jobs] all {len(sources)} companies failed for {desired_position!r} -- not caching")
    return matched


@dataclass
class _FetchResult:
    source: CompanySource
    postings: list[NormalizedJobPosting]
    error: Exception | None


async def _fetch_sources_concurrently_async(
    sources: list[CompanySource], desired_position: str, max_concurrency: int
) -> list[_FetchResult]:
    """Fetches every source's board concurrently, bounded by
    `max_concurrency` (a semaphore, not one task per company) -- see
    core/config.py's ats_max_concurrency. One shared httpx.AsyncClient for
    the whole batch, not one per company. Each company's outcome
    (postings or the isolatable error it hit) is captured individually --
    asyncio.gather is never allowed to let one company's exception cancel
    or discard another's already-fetched result.
    """
    title_matches = _title_matcher(desired_position)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch_one(client: httpx.AsyncClient, source: CompanySource) -> _FetchResult:
        fetch = FETCHERS_FILTERED_ASYNC[source.ats_platform]
        async with semaphore:
            try:
                postings = await fetch(client, source.ats_identifier, title_matches)
                return _FetchResult(source=source, postings=postings, error=None)
            except COMPANY_ISOLATABLE_ERRORS as exc:
                return _FetchResult(source=source, postings=[], error=exc)

    async with httpx.AsyncClient() as client:
        return list(await asyncio.gather(*(fetch_one(client, source) for source in sources)))


def _fetch_sources_concurrently(
    sources: list[CompanySource], desired_position: str, max_concurrency: int
) -> list[_FetchResult]:
    """Sync entry point run_targeted_ingestion actually calls -- wraps
    _fetch_sources_concurrently_async in its own event loop
    (asyncio.run), so the rest of this module (and its callers -- the
    sync FastAPI route, sync tests) never has to deal with async/await
    itself. Only the ATS fetch step runs concurrently; every DB write
    still happens afterward on the caller's single sync Session.
    """
    return asyncio.run(_fetch_sources_concurrently_async(sources, desired_position, max_concurrency))


def _get_cached_matches(
    db: Session, key: str, freshness_minutes: int
) -> list[JobPosting] | None:
    """Returns already-ingested matches if `key` (see
    query_normalization.cache_key) was fully ingested within
    `freshness_minutes`, else None (meaning: no fresh cache entry, caller
    should run the live pipeline).
    """
    cache_row = db.scalar(select(JobSearchCache).where(JobSearchCache.target_position == key))
    if cache_row is None:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=freshness_minutes)
    if cache_row.last_ingested_at < cutoff:
        return None  # stale -- caller falls through to a live pull

    needle = key.split(":", 1)[1] if ":" in key else key
    return list(
        db.scalars(
            select(JobPosting).where(
                JobPosting.title.ilike(f"%{needle}%"),
                JobPosting.is_active.is_(True),
            )
        )
    )


def _mark_position_ingested(db: Session, key: str) -> None:
    """Upsert job_search_cache so the next search for this exact cache
    key within freshness_minutes hits the cache.
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


def _persist_company_postings(
    db: Session,
    source: CompanySource,
    postings: list[NormalizedJobPosting],
    extraction_limit: int | None,
) -> list[JobPosting]:
    """DB-write half of the targeted-ingestion pipeline for one company --
    upsert + batched extraction for postings already fetched (concurrently,
    see _fetch_sources_concurrently) before this ever runs. Split from the
    fetch step so the I/O-bound fetch (safe to run concurrently across
    companies) and DB writes (must stay on the caller's single,
    non-thread-safe Session) are never interleaved across companies.
    """
    print(f"[jobs] {source.name}: {len(postings)} posting(s) match")
    company = _get_or_create_company(db, source)

    results: list[JobPosting] = []
    pending: list[tuple[JobPosting, str | None]] = []
    for posting in postings:
        job_posting, needs_extraction, new_hash = _upsert_job_posting(db, company, posting)
        if needs_extraction and (extraction_limit is None or len(pending) < extraction_limit):
            pending.append((job_posting, new_hash))
        results.append(job_posting)

    _sync_job_posting_skills_batch(db, pending, log_prefix="[jobs]")

    return results


def _title_matcher(desired_position: str) -> Callable[[str], bool]:
    """Case-insensitive substring match against a posting's raw title,
    using the same normalization as the cache key (query_normalization.
    normalize_query) so e.g. a live "SWE" search matches the same
    postings a "Software Engineer" search would. Simple on purpose --
    matching by extracted skills or semantic/embedding similarity is
    services/matching.py's job, later, not this. Returns a predicate
    (rather than filtering a list directly) so FETCHERS_FILTERED can
    apply it before a posting's description is even parsed -- see
    greenhouse.py's fetch_jobs_filtered.
    """
    needle = normalize_query(desired_position)
    if not needle:
        return lambda title: True
    return lambda title: needle in title.lower()


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
) -> bool:
    """Batch counterpart to the old one-OpenAI-call-per-posting flow:
    extracts skills for every (job_posting, new_hash) pair in `pending`
    using as few OpenAI calls as possible
    (see services/job_skill_extraction.extract_job_skills_batch, which
    internally chunks into groups of BATCH_SIZE), then applies each
    posting's result and stamps description_hash -- same "only stamped
    once extraction actually completes" rule as before, so a posting
    left out of `pending` by the caller's extraction_limit is still
    correctly flagged as needing extraction on the next run.

    Returns True unless the OpenAI call itself failed. On failure, the
    postings in `pending` are deliberately left with their hash unstamped
    (never marked as "extraction complete") and the exception is NOT
    re-raised -- an OpenAI outage/timeout must not roll back the job
    postings already upserted by the caller (they're still real, current
    postings even without skills yet), only skip extraction for this
    batch, retried automatically next time this company is searched
    (same reasoning as the extraction_limit skip path above).
    """
    if not pending:
        return True

    # No description at all -- nothing to send to the model, same
    # short-circuit the old per-posting path had.
    to_extract = [(jp, new_hash) for jp, new_hash in pending if jp.description]
    for job_posting, new_hash in pending:
        if not job_posting.description:
            job_posting.description_hash = new_hash

    if not to_extract:
        return True

    print(f"{log_prefix}   extracting skills: batch of {len(to_extract)} posting(s)")
    try:
        results = extract_job_skills_batch([jp.description for jp, _ in to_extract])
    except OpenAIError as exc:
        print(
            f"{log_prefix}   skill extraction FAILED ({type(exc).__name__}) -- {exc}; "
            f"{len(to_extract)} posting(s) left pending, retried next time"
        )
        return False

    _apply_job_skill_extractions_batch(db, to_extract, results)
    return True


def _bulk_resolve_skills(db: Session, skill_specs: list[tuple[str, str]]) -> dict[str, Skill]:
    """Resolves many (name, category) pairs to Skill rows in at most two
    round trips total (one SELECT ... IN, one bulk INSERT for anything
    missing) instead of one SELECT-plus-maybe-INSERT per skill name --
    the dominant N+1 source when extracting skills for a whole batch of
    postings at once, since each posting can name several skills. Keyed
    by lowercased name in the returned dict. Case-insensitive dedup
    within `skill_specs` mirrors repositories/skills.py's
    get_or_create_skill (first category wins for a name repeated within
    this batch).

    Safe against a uniqueness race with a concurrent request creating the
    same skill name: on_conflict_do_nothing's RETURNING won't include a
    row for a name that lost the race, so anything still missing after
    the bulk insert is re-selected once more (same guarantee
    get_or_create_skill's docstring already accepts at the single-skill
    scale, just applied across a batch).
    """
    by_lower: dict[str, tuple[str, str]] = {}
    for name, category in skill_specs:
        key = name.strip().lower()
        by_lower.setdefault(key, (name.strip(), category))

    if not by_lower:
        return {}

    resolved: dict[str, Skill] = {
        skill.name.strip().lower(): skill
        for skill in db.scalars(select(Skill).where(func.lower(Skill.name).in_(by_lower.keys())))
    }

    missing = [(name, category) for key, (name, category) in by_lower.items() if key not in resolved]
    if missing:
        stmt = (
            pg_insert(Skill.__table__)
            .values([{"name": name, "category": category} for name, category in missing])
            .on_conflict_do_nothing(index_elements=[Skill.__table__.c.name])
            .returning(Skill.__table__.c.id, Skill.__table__.c.name, Skill.__table__.c.category)
        )
        for row in db.execute(stmt):
            resolved[row.name.strip().lower()] = Skill(id=row.id, name=row.name, category=row.category)

        still_missing_keys = [key for key, _ in ((n.strip().lower(), c) for n, c in missing) if key not in resolved]
        if still_missing_keys:
            for skill in db.scalars(select(Skill).where(func.lower(Skill.name).in_(still_missing_keys))):
                resolved[skill.name.strip().lower()] = skill

    return resolved


def _apply_job_skill_extractions_batch(
    db: Session,
    to_extract: list[tuple[JobPosting, str | None]],
    results: list[JobSkillExtractionResult],
) -> None:
    """Batched counterpart to the old per-posting apply step: resolves
    every skill named anywhere in this whole batch in one round trip (see
    _bulk_resolve_skills) and issues one bulk upsert for every
    job_posting_skill row instead of one statement per (posting, skill)
    pair -- same per-posting semantics as before (technical wins on a
    name collision within one posting's own lists, stale links for that
    posting are removed), just far fewer SQL statements to produce them.
    """
    per_posting: list[tuple[JobPosting, str | None, dict[str, tuple[str, ExtractedJobSkill]]]] = []
    all_skill_specs: list[tuple[str, str]] = []

    for (job_posting, new_hash), result in zip(to_extract, results):
        by_name: dict[str, tuple[str, ExtractedJobSkill]] = {}
        for item in result.required_skills:
            by_name.setdefault(item.skill.strip().lower(), ("required", item))
        for item in result.preferred_skills:
            by_name.setdefault(item.skill.strip().lower(), ("preferred", item))
        per_posting.append((job_posting, new_hash, by_name))
        for _, item in by_name.values():
            all_skill_specs.append((item.skill, item.category))

    resolved_skills = _bulk_resolve_skills(db, all_skill_specs)

    posting_ids = [jp.id for jp, _, _ in per_posting]
    existing_by_posting: dict[uuid.UUID, set[uuid.UUID]] = {}
    if posting_ids:
        for posting_id, skill_id in db.execute(
            select(job_posting_skill.c.job_posting_id, job_posting_skill.c.skill_id).where(
                job_posting_skill.c.job_posting_id.in_(posting_ids)
            )
        ):
            existing_by_posting.setdefault(posting_id, set()).add(skill_id)

    stale_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
    upsert_rows: list[dict] = []

    for job_posting, new_hash, by_name in per_posting:
        new_skill_ids: set[uuid.UUID] = set()
        for requirement_level, item in by_name.values():
            skill = resolved_skills[item.skill.strip().lower()]
            new_skill_ids.add(skill.id)
            upsert_rows.append(
                {
                    "job_posting_id": job_posting.id,
                    "skill_id": skill.id,
                    "requirement_level": requirement_level,
                    "evidence": item.evidence,
                }
            )
        stale = existing_by_posting.get(job_posting.id, set()) - new_skill_ids
        stale_pairs.extend((job_posting.id, skill_id) for skill_id in stale)
        job_posting.description_hash = new_hash

    if stale_pairs:
        db.execute(
            delete(job_posting_skill).where(
                tuple_(job_posting_skill.c.job_posting_id, job_posting_skill.c.skill_id).in_(
                    stale_pairs
                )
            )
        )

    if upsert_rows:
        stmt = pg_insert(job_posting_skill).values(upsert_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[job_posting_skill.c.job_posting_id, job_posting_skill.c.skill_id],
            set_={
                "requirement_level": stmt.excluded.requirement_level,
                "evidence": stmt.excluded.evidence,
            },
        )
        db.execute(stmt)


if __name__ == "__main__":
    # Manual trigger: `python -m app.ingestion.runner` from backend/, venv
    # active. scheduler/refresh_ats.py (later) will call run_ingestion()
    # the same way, just on a schedule instead of by hand.
    run_ingestion()
