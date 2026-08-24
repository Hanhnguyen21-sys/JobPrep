"""Tests for Phase 2 item 5: _fetch_sources_concurrently_async
(ingestion/runner.py) -- bounded concurrency across companies, proof of
overlap, and per-company failure isolation within the concurrent fetch
itself (an HTTPError for one company must not cancel/discard the others'
results via asyncio.gather).

Uses a fake async client (not real httpx.AsyncClient/network) with an
artificial `await asyncio.sleep(delay)` per call -- deterministic,
reproducible, no live ATS dependency.
"""

import asyncio
import time

import httpx

from app.ingestion import runner
from app.ingestion.runner import CompanySource


class _TrackingAsyncClient:
    """Records concurrent-call-count high-water-mark and applies a fixed
    artificial delay per .get() -- lets tests assert both "never more
    than N at once" and "wall time reflects overlap, not sequencing."
    """

    def __init__(self, delay: float, tracker: dict):
        self.delay = delay
        self.tracker = tracker

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, **kwargs):
        self.tracker["current"] += 1
        self.tracker["max"] = max(self.tracker["max"], self.tracker["current"])
        await asyncio.sleep(self.delay)
        self.tracker["current"] -= 1

        request = httpx.Request("GET", url)
        if "boards-api.greenhouse.io" in url:
            return httpx.Response(200, json={"jobs": []}, request=request)
        return httpx.Response(200, json=[], request=request)


def _sources(n: int) -> list[CompanySource]:
    return [
        CompanySource(
            name=f"Company {i}",
            ats_platform="greenhouse" if i % 2 == 0 else "lever",
            ats_identifier=f"c{i}",
        )
        for i in range(n)
    ]


def test_concurrency_never_exceeds_configured_limit(monkeypatch):
    tracker = {"current": 0, "max": 0}
    monkeypatch.setattr(runner.httpx, "AsyncClient", lambda: _TrackingAsyncClient(0.03, tracker))

    sources = _sources(10)
    max_concurrency = 3

    asyncio.run(
        runner._fetch_sources_concurrently_async(sources, "engineer", max_concurrency)
    )

    assert tracker["max"] <= max_concurrency
    assert tracker["max"] > 1  # sanity: concurrency actually happened, this isn't accidentally serial


def test_concurrent_fetch_overlaps_wall_time_is_not_sequential(monkeypatch):
    tracker = {"current": 0, "max": 0}
    delay = 0.05
    monkeypatch.setattr(runner.httpx, "AsyncClient", lambda: _TrackingAsyncClient(delay, tracker))

    sources = _sources(8)
    sequential_estimate = delay * len(sources)

    start = time.perf_counter()
    asyncio.run(runner._fetch_sources_concurrently_async(sources, "engineer", max_concurrency=4))
    elapsed = time.perf_counter() - start

    # 8 companies at concurrency 4 -> ~2 "rounds" of delay, well under
    # what fully sequential (8 rounds) would take.
    assert elapsed < sequential_estimate * 0.75


def test_one_company_error_does_not_cancel_or_discard_others():
    class _PartialFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def get(self, url, **kwargs):
            if "c1" in url:
                raise httpx.ConnectError("simulated ATS outage", request=httpx.Request("GET", url))
            request = httpx.Request("GET", url)
            if "boards-api.greenhouse.io" in url:
                return httpx.Response(200, json={"jobs": []}, request=request)
            return httpx.Response(200, json=[], request=request)

    import unittest.mock

    with unittest.mock.patch("httpx.AsyncClient", lambda: _PartialFailClient()):
        sources = _sources(3)
        results = asyncio.run(
            runner._fetch_sources_concurrently_async(sources, "engineer", max_concurrency=3)
        )

    assert len(results) == 3
    errored = [r for r in results if r.error is not None]
    succeeded = [r for r in results if r.error is None]
    assert len(errored) == 1
    assert errored[0].source.ats_identifier == "c1"
    assert len(succeeded) == 2
