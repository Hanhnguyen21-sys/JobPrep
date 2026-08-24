"""Lever Postings API client -- public, unauthenticated endpoint -- no API
key needed. Docs: https://github.com/lever/postings-api

Returns NormalizedJobPosting, the same shape greenhouse.py returns, so
ingestion/runner.py doesn't need to know which ATS a posting came from.

Two entry points, mirroring greenhouse.py's fetch_jobs/fetch_jobs_filtered
split (see that module's docstring) -- Lever's description is already
plain text (no HTML-stripping step to skip), but filtering before
constructing NormalizedJobPosting objects for non-matching postings is
still avoided work, and it keeps the two ATS clients' interfaces
symmetric for ingestion/runner.py's FETCHERS_FILTERED dispatch.
"""

from datetime import datetime, timezone
from typing import Callable

import httpx

from app.core.config import get_settings
from app.ingestion.common import NormalizedJobPosting

BASE_URL = "https://api.lever.co/v0/postings"


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.ats_connect_timeout_seconds,
        read=settings.ats_read_timeout_seconds,
        write=settings.ats_read_timeout_seconds,
        pool=settings.ats_connect_timeout_seconds,
    )


def _parse_epoch_ms(value: int | None) -> datetime | None:
    """Lever gives `createdAt` in epoch milliseconds and doesn't expose a
    separate "last updated" timestamp -- see module docstring caveat.
    """
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _fetch_raw(site: str) -> list[dict]:
    url = f"{BASE_URL}/{site}"
    response = httpx.get(url, params={"mode": "json"}, timeout=_timeout())
    response.raise_for_status()
    return response.json()


def _to_posting(posting: dict) -> NormalizedJobPosting:
    return NormalizedJobPosting(
        external_id=posting["id"],
        title=posting["text"],
        location=(posting.get("categories") or {}).get("location"),
        description=posting.get("descriptionPlain") or None,
        url=posting.get("hostedUrl"),
        source_updated_at=_parse_epoch_ms(posting.get("createdAt")),
    )


def fetch_jobs(site: str) -> list[NormalizedJobPosting]:
    """Fetch every open posting for one Lever site."""
    return [_to_posting(p) for p in _fetch_raw(site)]


def fetch_jobs_filtered(
    site: str, title_matches: Callable[[str], bool]
) -> list[NormalizedJobPosting]:
    """Same live fetch as fetch_jobs(), but only constructs postings whose
    raw title satisfies `title_matches` -- see module docstring.
    """
    return [_to_posting(p) for p in _fetch_raw(site) if title_matches(p["text"])]


async def _fetch_raw_async(client: httpx.AsyncClient, site: str) -> list[dict]:
    url = f"{BASE_URL}/{site}"
    response = await client.get(url, params={"mode": "json"}, timeout=_timeout())
    response.raise_for_status()
    return response.json()


async def fetch_jobs_filtered_async(
    client: httpx.AsyncClient, site: str, title_matches: Callable[[str], bool]
) -> list[NormalizedJobPosting]:
    """Async counterpart to fetch_jobs_filtered() -- see greenhouse.py's
    fetch_jobs_filtered_async docstring.
    """
    raw = await _fetch_raw_async(client, site)
    return [_to_posting(p) for p in raw if title_matches(p["text"])]
