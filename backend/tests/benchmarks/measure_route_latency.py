"""Measures POST /jobs/match's own response latency after Phase 3 --
called directly as a plain function (real DB, no HTTP layer) with a real
SessionLocal() so every DB read/write is genuine, but background_tasks
is a real fastapi.BackgroundTasks() that is never actually drained (that
only happens via Starlette's ASGI machinery after a real HTTP response,
which this script doesn't go through) -- so this measures exactly what
the route itself does before handing off to the background worker:
DB reads + one enqueue attempt, zero ATS/OpenAI calls, always.

LOCAL INTEGRATION measurement (real database), not a production timing.
Separate from run_benchmark.py, which measures run_targeted_ingestion
itself (i.e. how long the background refresh takes once it runs) --
Phase 3 didn't change that function's internals, only where/when it gets
called from.
"""

import statistics
import time
import uuid

from fastapi import BackgroundTasks

from app.api.routes.jobs import find_matching_jobs
from app.db.session import SessionLocal
from app.models.user import User
from sqlalchemy import text


class _FakeResponse:
    status_code = 200


def _cleanup(position: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text("delete from job_search_task where cache_key like :p").bindparams(p=f"%{position.lower()}%")
        )
        db.execute(
            text("delete from job_search_cache where target_position like :p").bindparams(p=f"%{position.lower()}%")
        )
        db.commit()
    finally:
        db.close()


def main() -> None:
    timings = []
    for i in range(11):  # 1 warmup + 10 measured
        position = f"Benchmark Nonexistent Role {uuid.uuid4().hex[:8]}"
        user = User(id=uuid.uuid4(), email="bench@example.com", target_position=position)

        db = SessionLocal()
        try:
            start = time.perf_counter()
            result = find_matching_jobs(
                background_tasks=BackgroundTasks(),
                response=_FakeResponse(),
                current_user=user,
                db=db,
            )
            elapsed = time.perf_counter() - start
        finally:
            db.close()
        _cleanup(position)

        if i > 0:
            timings.append(elapsed)
        if i == 1:
            print(f"first measured call: freshness={result.freshness!r} task_id={result.task_id}")

    timings.sort()
    p50 = timings[len(timings) // 2]
    p95 = timings[int(round(0.95 * (len(timings) - 1)))]
    print(f"/jobs/match route latency (no data exists -> 'pending' path, real DB, N={len(timings)}):")
    print(f"  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  min={min(timings)*1000:.1f}ms  max={max(timings)*1000:.1f}ms")


if __name__ == "__main__":
    main()
