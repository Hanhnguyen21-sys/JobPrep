"""Runs the fixed benchmark workload against ingestion/runner.py's
run_targeted_ingestion() and prints a report. See bench_harness.py's
module docstring for what is real (the database) vs. simulated (ATS/
OpenAI latency) in these numbers -- LOCAL INTEGRATION benchmark, not
production timings.

Usage (from backend/, venv active):
    python -m tests.benchmarks.run_benchmark [--label "baseline"]

The workload is identical every time this is run -- only the code under
test (ingestion/runner.py et al.) changes between phases, so numbers are
comparable across `--label baseline / phase1 / phase2 / phase3`.
"""

import argparse
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.db.session import SessionLocal
from app.ingestion import greenhouse
from app.ingestion.query_normalization import cache_key
from app.ingestion.runner import run_targeted_ingestion
from app.models.search_cache import JobSearchCache
from app.services import job_skill_extraction
from tests.benchmarks.bench_harness import (
    BENCH_QUERY_VARIANTS,
    CANONICAL_QUERY,
    DEFAULT_ATS_LATENCY,
    DEFAULT_OPENAI_LATENCY,
    FakeAsyncClient,
    FakeAtsConfig,
    bench_companies,
    cleanup_bench_data,
    make_fake_extract_job_skills_batch,
    make_fake_httpx_get,
)

WARMUP_RUNS = 1
MEASURED_RUNS = 10


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct * (len(ordered) - 1))))
    return ordered[idx]


def _instrumented_run(
    config: FakeAtsConfig,
    openai_latency: float,
    query: str,
    freshness_minutes: int = 60,
    cleanup_before: bool = True,
    cleanup_after: bool = True,
):
    """One call to run_targeted_ingestion, with all counters reset and
    collected around it. Returns (wall_seconds, counters_dict, matched_count).

    `cleanup_before`/`cleanup_after` default to True (every call starts and
    ends from a clean slate -- used by cold/stale scenarios, where each
    measured run must be independent). The warm-search scenario passes
    both False around a priming call + the measured call so the primed
    cache/postings survive between them, then cleans up once at the end.
    """
    counters = {"sql": 0, "commits": 0, "ats_calls": 0, "openai_calls": 0, "html_strips": 0}

    real_get = make_fake_httpx_get(config)
    real_extract = make_fake_extract_job_skills_batch(openai_latency)
    real_strip = greenhouse._strip_html

    def counted_get(url, **kwargs):
        # Kept for the pre-Phase-2 sync fetch path (harmless no-op once
        # run_targeted_ingestion switched to the async client below --
        # nothing calls httpx.get directly anymore after that change).
        counters["ats_calls"] += 1
        return real_get(url, **kwargs)

    class _CountingAsyncClient(FakeAsyncClient):
        async def get(self, url, **kwargs):
            counters["ats_calls"] += 1
            return await super().get(url, **kwargs)

    def counted_extract(descriptions):
        counters["openai_calls"] += 1
        return real_extract(descriptions)

    def counted_strip(html):
        counters["html_strips"] += 1
        return real_strip(html)

    from sqlalchemy import event

    from app.db.session import engine

    def sql_hook(conn, cursor, statement, parameters, context, executemany):
        counters["sql"] += 1

    event.listen(engine, "before_cursor_execute", sql_hook)

    db = SessionLocal()
    if cleanup_before:
        cleanup_bench_data(db)

    real_commit = db.commit

    def counted_commit():
        counters["commits"] += 1
        return real_commit()

    db.commit = counted_commit

    try:
        with patch("httpx.get", counted_get), patch(
            "httpx.AsyncClient", lambda: _CountingAsyncClient(config)
        ), patch("app.ingestion.runner.extract_job_skills_batch", counted_extract), patch(
            "app.ingestion.greenhouse._strip_html", counted_strip
        ):
            start = time.perf_counter()
            matched = run_targeted_ingestion(
                db,
                query,
                companies=bench_companies(),
                freshness_minutes=freshness_minutes,
            )
            wall = time.perf_counter() - start
    finally:
        event.remove(engine, "before_cursor_execute", sql_hook)
        if cleanup_after:
            cleanup_bench_data(db)
        db.close()

    return wall, counters, len(matched)


def _summarize(label: str, timings: list[float], last_counters: dict, matched_count: int) -> dict:
    return {
        "scenario": label,
        "p50": _percentile(timings, 0.5),
        "p95": _percentile(timings, 0.95),
        "min": min(timings),
        "max": max(timings),
        "runs": len(timings),
        "sql": last_counters["sql"],
        "commits": last_counters["commits"],
        "ats_calls": last_counters["ats_calls"],
        "openai_calls": last_counters["openai_calls"],
        "html_strips": last_counters["html_strips"],
        "matched": matched_count,
    }


def scenario_cold_search() -> dict:
    """No cache, no existing matching jobs -- full live pipeline every run."""
    config = FakeAtsConfig(matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY)
    timings = []
    counters = {}
    matched = 0
    for i in range(WARMUP_RUNS + MEASURED_RUNS):
        wall, counters, matched = _instrumented_run(config, DEFAULT_OPENAI_LATENCY, CANONICAL_QUERY, freshness_minutes=60)
        if i >= WARMUP_RUNS:
            timings.append(wall)
    return _summarize("cold_search", timings, counters, matched)


def scenario_warm_search() -> dict:
    """Cache populated and fresh -- should hit the DB-only fast path.

    Each iteration: prime (unmeasured cold call, cache/postings left in
    place afterward) then immediately measure a second call for the same
    query, which should be a cache hit (zero ATS/OpenAI calls). Cleans up
    fully at the very end of each iteration so the next iteration starts
    from a known state too.
    """
    config = FakeAtsConfig(matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY)
    timings = []
    counters = {}
    matched = 0
    for i in range(WARMUP_RUNS + MEASURED_RUNS):
        _instrumented_run(  # priming call, not measured
            config, DEFAULT_OPENAI_LATENCY, CANONICAL_QUERY,
            freshness_minutes=60, cleanup_before=True, cleanup_after=False,
        )
        wall, counters, matched = _instrumented_run(
            config, DEFAULT_OPENAI_LATENCY, CANONICAL_QUERY,
            freshness_minutes=60, cleanup_before=False, cleanup_after=True,
        )
        if i >= WARMUP_RUNS:
            timings.append(wall)
    return _summarize("warm_search", timings, counters, matched)


def scenario_stale_search() -> dict:
    """Cache row exists but older than freshness_minutes -- falls through
    to the live pipeline, same cost as cold, but exercises the
    "cache exists but expired" branch specifically.
    """
    config = FakeAtsConfig(matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY)
    timings = []
    counters = {}
    matched = 0
    for i in range(WARMUP_RUNS + MEASURED_RUNS):
        db = SessionLocal()
        cleanup_bench_data(db)
        # Seed a stale cache row directly (2 hours old, default freshness is 60 min).
        db.execute(
            JobSearchCache.__table__.insert().values(
                target_position=cache_key(CANONICAL_QUERY),
                last_ingested_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        db.commit()
        db.close()

        # cleanup_before=False -- the stale cache row just seeded above
        # must survive into this call; _instrumented_run's default
        # cleanup_before=True would delete it before run_targeted_ingestion
        # ever sees it, making this indistinguishable from cold_search.
        wall, counters, matched = _instrumented_run(
            config, DEFAULT_OPENAI_LATENCY, CANONICAL_QUERY, freshness_minutes=60, cleanup_before=False
        )
        if i >= WARMUP_RUNS:
            timings.append(wall)
    return _summarize("stale_search", timings, counters, matched)


def scenario_query_variants() -> list[dict]:
    """Pre-populate the cache with ONLY the canonical query, then check
    which variants hit vs. miss against today's exact-string cache key.
    """
    db = SessionLocal()
    cleanup_bench_data(db)
    db.execute(
        JobSearchCache.__table__.insert().values(
            target_position=cache_key(CANONICAL_QUERY),
            last_ingested_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.close()

    results = []
    config = FakeAtsConfig(matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY)
    for variant in BENCH_QUERY_VARIANTS:
        # cleanup_before/after=False -- the canonical cache row seeded
        # above (and any it creates along the way) must survive across
        # every variant check in this loop; only clean up once, after
        # the whole loop finishes (below).
        wall, counters, matched = _instrumented_run(
            config, DEFAULT_OPENAI_LATENCY, variant, freshness_minutes=60,
            cleanup_before=False, cleanup_after=False,
        )
        hit = counters["ats_calls"] == 0
        results.append({"query": variant, "cache_hit": hit, "wall_seconds": wall})

    db = SessionLocal()
    cleanup_bench_data(db)
    db.close()
    return results


def scenario_partial_ats_failure() -> dict:
    """2 of 8 companies return a simulated ATS outage (HTTP 503) --
    the request must still return matches from the healthy 6.
    """
    config = FakeAtsConfig(
        matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY, failing_indices=frozenset({2, 5})
    )
    wall, counters, matched = _instrumented_run(config, DEFAULT_OPENAI_LATENCY, CANONICAL_QUERY, freshness_minutes=60)
    return {
        "scenario": "partial_ats_failure",
        "wall_seconds": wall,
        "matched": matched,
        "expected_matched": 6 * 1,  # 6 healthy companies * MATCHING_PER_COMPANY
        "ats_calls": counters["ats_calls"],
    }


def scenario_slow_openai() -> dict:
    """OpenAI simulated at 3s/call instead of the default 0.3s."""
    config = FakeAtsConfig(matching_title=CANONICAL_QUERY, latency_seconds=DEFAULT_ATS_LATENCY)
    wall, counters, matched = _instrumented_run(config, openai_latency=3.0, query=CANONICAL_QUERY, freshness_minutes=60)
    return {"scenario": "slow_openai", "wall_seconds": wall, "matched": matched, "openai_calls": counters["openai_calls"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    args = parser.parse_args()

    print(f"\n===== Benchmark: {args.label} =====")
    print(f"({WARMUP_RUNS} warmup + {MEASURED_RUNS} measured runs per timed scenario)\n")

    for scenario_fn in [scenario_cold_search, scenario_warm_search, scenario_stale_search]:
        result = scenario_fn()
        print(
            f"{result['scenario']:15s} p50={result['p50']*1000:7.1f}ms  p95={result['p95']*1000:7.1f}ms  "
            f"min={result['min']*1000:7.1f}ms  max={result['max']*1000:7.1f}ms  "
            f"sql={result['sql']:4d}  commits={result['commits']:3d}  "
            f"ats_calls={result['ats_calls']:2d}  openai_calls={result['openai_calls']:2d}  "
            f"html_strips={result['html_strips']:4d}  matched={result['matched']}"
        )

    print("\nquery variants (cache pre-populated with canonical 'Software Engineer' only):")
    for v in scenario_query_variants():
        print(f"  {v['query']!r:30s} cache_hit={v['cache_hit']!s:5s} wall={v['wall_seconds']*1000:7.1f}ms")

    pf = scenario_partial_ats_failure()
    print(
        f"\npartial_ats_failure: wall={pf['wall_seconds']*1000:.1f}ms  matched={pf['matched']}"
        f"  expected={pf['expected_matched']}  ats_calls={pf['ats_calls']}"
    )

    so = scenario_slow_openai()
    print(
        f"slow_openai:         wall={so['wall_seconds']*1000:.1f}ms  matched={so['matched']}"
        f"  openai_calls={so['openai_calls']}"
    )
    print()


if __name__ == "__main__":
    main()
