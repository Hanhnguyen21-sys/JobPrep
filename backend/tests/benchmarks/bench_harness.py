"""Deterministic benchmark harness for POST /jobs/match's underlying
run_targeted_ingestion() pipeline (ingestion/runner.py).

LABEL: this is a LOCAL INTEGRATION benchmark. It runs against the real
configured database (app.db.session.SessionLocal / the project's actual
Postgres), exercising real SQL statements and commits -- but the two
genuinely external, slow, non-deterministic services are replaced with
deterministic delays, per the project's benchmarking rules:

  - Greenhouse/Lever HTTP calls: `httpx.get` is monkeypatched to return
    synthetic, realistic-shaped fixture payloads after
    time.sleep(ats_latency_seconds) -- greenhouse.py/lever.py's own
    parsing/HTML-stripping logic still runs for real on that fixture data,
    only the network I/O is faked.
  - OpenAI skill extraction: `extract_job_skills_batch` is monkeypatched
    to return a synthetic result after time.sleep(openai_latency_seconds)
    -- everything downstream (dedup, get_or_create_skill, job_posting_skill
    upsert) still runs for real against the real database.

This is NOT a measurement of real Greenhouse/Lever/OpenAI latency -- it is
a reproducible way to measure the *architectural* behavior of the
ingestion pipeline (sequential vs. concurrent fetch, per-item vs. batched
SQL, HTML-strip call counts, extraction-skip behavior) with numbers that
don't vary run to run because of live network/API conditions. Absolute
seconds here should not be read as production latency predictions --
relative comparisons between baseline/Phase 1/Phase 2/Phase 3 ARE
meaningful, since the exact same workload and simulated delays are reused
every time (see BENCH_QUERY_VARIANTS / scenario functions below, unchanged
across phases).

Companies used are synthetic ("bench-co-N", passed via the `companies=`
override both run_ingestion/run_targeted_ingestion already support) and
are deleted from the database before and after every scenario, so this
never pollutes the real `companies`/`job_postings` data used by the real
app.
"""

from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx
from sqlalchemy import delete, event, text

from app.db.session import SessionLocal, engine
from app.ingestion import runner
from app.ingestion.query_normalization import cache_key
from app.models.company import Company
from app.models.job_posting import JobPosting, job_posting_skill
from app.models.search_cache import JobSearchCache
from app.services import job_skill_extraction

BENCH_COMPANY_PREFIX = "bench-co-"
NUM_COMPANIES = 8
POSTINGS_PER_COMPANY = 14  # 8 * 14 = 112 total postings -- satisfies ">=100 jobs" requirement
MATCHING_PER_COMPANY = 1  # only a small number match the target title, per requirement

DEFAULT_ATS_LATENCY = 0.05  # seconds, simulated per ATS HTTP call
DEFAULT_OPENAI_LATENCY = 0.08  # seconds, simulated per OpenAI batch call

LOREM = (
    "<p>Requirements: Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, "
    "distributed systems, REST APIs, CI/CD, Git.</p>" * 4
)

BENCH_QUERY_VARIANTS = [
    "Software Engineer",
    "software   engineer",
    "software-engineer",
    "SWE",
    "Software Engineer Intern",
]
CANONICAL_QUERY = "Software Engineer"


def bench_companies() -> list[runner.CompanySource]:
    sources = []
    for i in range(NUM_COMPANIES):
        platform = "greenhouse" if i % 2 == 0 else "lever"
        sources.append(
            runner.CompanySource(
                name=f"Bench Co {i}",
                ats_platform=platform,
                ats_identifier=f"{BENCH_COMPANY_PREFIX}{i}",
            )
        )
    return sources


def _index_from_identifier(identifier: str) -> int:
    return int(identifier.removeprefix(BENCH_COMPANY_PREFIX))


def _greenhouse_payload(idx: int, matching_title: str) -> dict:
    jobs = []
    for j in range(POSTINGS_PER_COMPANY):
        title = matching_title if j < MATCHING_PER_COMPANY else f"Product Designer {idx}-{j}"
        jobs.append(
            {
                "id": 1000 * idx + j,
                "title": title,
                "location": {"name": "Remote"},
                "content": LOREM,
                "absolute_url": f"https://boards.greenhouse.io/bench/{idx}/{j}",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    return {"jobs": jobs}


def _lever_payload(idx: int, matching_title: str) -> list[dict]:
    postings = []
    for j in range(POSTINGS_PER_COMPANY):
        title = matching_title if j < MATCHING_PER_COMPANY else f"Product Designer {idx}-{j}"
        postings.append(
            {
                "id": f"c{idx}-p{j}",
                "text": title,
                "categories": {"location": "Remote"},
                "descriptionPlain": LOREM,
                "hostedUrl": f"https://jobs.lever.co/bench/{idx}/{j}",
                "createdAt": 1700000000000,
            }
        )
    return postings


@dataclass
class FakeAtsConfig:
    """Mutable knobs the benchmark scenarios flip between runs -- read by
    `fake_httpx_get` on every call, so one monkeypatch installed for the
    whole harness session can express every scenario (matching title,
    per-company latency, which companies fail).
    """

    matching_title: str = CANONICAL_QUERY
    latency_seconds: float = DEFAULT_ATS_LATENCY
    failing_indices: frozenset[int] = field(default_factory=frozenset)


def make_fake_httpx_get(config: FakeAtsConfig) -> Callable:
    def fake_get(url: str, *, params=None, timeout=None):
        time.sleep(config.latency_seconds)
        request = httpx.Request("GET", url)

        if "boards-api.greenhouse.io" in url:
            board_token = url.split("/")[-2]  # .../boards/{token}/jobs
            idx = _index_from_identifier(board_token)
            if idx in config.failing_indices:
                return httpx.Response(503, request=request, text="simulated ATS outage")
            return httpx.Response(200, json=_greenhouse_payload(idx, config.matching_title), request=request)

        if "api.lever.co" in url:
            idx = _index_from_identifier(url.split("/")[-1])
            if idx in config.failing_indices:
                return httpx.Response(503, request=request, text="simulated ATS outage")
            return httpx.Response(200, json=_lever_payload(idx, config.matching_title), request=request)

        raise AssertionError(f"unexpected URL in benchmark: {url}")

    return fake_get


class FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used by ingestion/runner.py's
    concurrent fetch (_fetch_sources_concurrently_async, added in Phase
    2) -- same fixture data / simulated latency / failure injection as
    make_fake_httpx_get above, just for the async call path. Constructing
    this IS the "httpx.AsyncClient()" call site being patched, so it
    doubles as its own async context manager.
    """

    def __init__(self, config: FakeAtsConfig):
        self.config = config

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url: str, *, params=None, timeout=None):
        import asyncio as _asyncio

        await _asyncio.sleep(self.config.latency_seconds)
        request = httpx.Request("GET", url)

        if "boards-api.greenhouse.io" in url:
            idx = _index_from_identifier(url.split("/")[-2])
            if idx in self.config.failing_indices:
                return httpx.Response(503, request=request, text="simulated ATS outage")
            return httpx.Response(
                200, json=_greenhouse_payload(idx, self.config.matching_title), request=request
            )

        if "api.lever.co" in url:
            idx = _index_from_identifier(url.split("/")[-1])
            if idx in self.config.failing_indices:
                return httpx.Response(503, request=request, text="simulated ATS outage")
            return httpx.Response(
                200, json=_lever_payload(idx, self.config.matching_title), request=request
            )

        raise AssertionError(f"unexpected URL in benchmark: {url}")


def make_fake_extract_job_skills_batch(latency_seconds: float) -> Callable:
    def fake_extract(descriptions: list[str]):
        time.sleep(latency_seconds)
        return [
            job_skill_extraction.JobSkillExtractionResult(
                required_skills=[
                    job_skill_extraction.ExtractedJobSkill(
                        skill="Python", category="technical", evidence="Requirements: Python"
                    )
                ],
                preferred_skills=[],
            )
            for _ in descriptions
        ]

    return fake_extract


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


@dataclass
class RunMetrics:
    wall_seconds: float = 0.0
    sql_statements: int = 0
    commits: int = 0
    ats_requests: int = 0
    openai_calls: int = 0
    html_strip_calls: int = 0
    matched_count: int = 0
    max_concurrent_ats: int = 1


@contextmanager
def _count_sql_statements():
    count = 0

    def _hook(conn, cursor, statement, parameters, context, executemany):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        yield lambda: count
    finally:
        event.remove(engine, "before_cursor_execute", _hook)


def cleanup_bench_data(db) -> None:
    """Deletes every trace of synthetic benchmark companies/postings and
    benchmark query-variant cache rows -- called before AND after every
    scenario so runs are independent and the real `companies` table this
    benchmark borrows (via the `companies=` override) is never left dirty.
    """
    company_ids = list(
        db.scalars(
            text("select id from companies where ats_identifier like :prefix").bindparams(
                prefix=f"{BENCH_COMPANY_PREFIX}%"
            )
        )
    )
    if company_ids:
        posting_ids = list(
            db.scalars(
                text(
                    "select id from job_postings where company_id = any(:ids)"
                ).bindparams(ids=company_ids)
            )
        )
        if posting_ids:
            db.execute(delete(job_posting_skill).where(job_posting_skill.c.job_posting_id.in_(posting_ids)))
            db.execute(delete(JobPosting).where(JobPosting.id.in_(posting_ids)))
        db.execute(delete(Company).where(Company.id.in_(company_ids)))

    # Delete by cache_key() (the real, versioned key runner.py actually
    # writes -- see query_normalization.py) rather than hand-duplicating
    # its normalization logic here, so this cleanup can't silently drift
    # out of sync with a future normalization-scheme change again.
    keys = [cache_key(q) for q in BENCH_QUERY_VARIANTS]
    db.execute(delete(JobSearchCache).where(JobSearchCache.target_position.in_(keys)))
    db.commit()
