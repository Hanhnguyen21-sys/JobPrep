"""Greenhouse Job Board API client.

Public, unauthenticated endpoint -- no API key needed to list a company's
postings. Docs: https://developers.greenhouse.io/job-board.html

Returns NormalizedJobPosting so ingestion/runner.py doesn't need to know
this data came from Greenhouse specifically -- lever.py returns the same
shape from a completely different response format.

Two entry points, sharing _fetch_raw/_to_posting:
- fetch_jobs() -- every posting, HTML-stripped. Used by the broad path
  (run_ingestion), which needs every posting's description regardless of
  any search term.
- fetch_jobs_filtered() -- only HTML-strips (BeautifulSoup) postings whose
  title survives a caller-supplied predicate, checked against the RAW
  title before any parsing happens. Used by the targeted/on-demand path
  (ingestion/runner.py's _ingest_company_for_position): a big board can
  have 100+ postings where only a handful match a given search, and
  stripping HTML from the rest just to discard them a moment later is
  wasted work.
"""

from datetime import datetime
from typing import Callable

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.ingestion.common import NormalizedJobPosting

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.ats_connect_timeout_seconds,
        read=settings.ats_read_timeout_seconds,
        write=settings.ats_read_timeout_seconds,
        pool=settings.ats_connect_timeout_seconds,
    )


def _strip_html(html: str | None) -> str | None:
    if not html:
        return None
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip() or None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _fetch_raw(board_token: str) -> list[dict]:
    url = f"{BASE_URL}/{board_token}/jobs"
    response = httpx.get(url, params={"content": "true"}, timeout=_timeout())
    response.raise_for_status()
    return response.json().get("jobs", [])


def _to_posting(job: dict) -> NormalizedJobPosting:
    return NormalizedJobPosting(
        external_id=str(job["id"]),
        title=job["title"],
        location=(job.get("location") or {}).get("name"),
        description=_strip_html(job.get("content")),
        url=job.get("absolute_url"),
        source_updated_at=_parse_datetime(job.get("updated_at")),
    )


def fetch_jobs(board_token: str) -> list[NormalizedJobPosting]:
    """Fetch every open posting for one Greenhouse board."""
    return [_to_posting(job) for job in _fetch_raw(board_token)]


def fetch_jobs_filtered(
    board_token: str, title_matches: Callable[[str], bool]
) -> list[NormalizedJobPosting]:
    """Same live fetch as fetch_jobs(), but HTML-strips only postings
    whose raw title satisfies `title_matches` -- see module docstring.
    """
    return [
        _to_posting(job) for job in _fetch_raw(board_token) if title_matches(job["title"])
    ]


async def _fetch_raw_async(client: httpx.AsyncClient, board_token: str) -> list[dict]:
    url = f"{BASE_URL}/{board_token}/jobs"
    response = await client.get(url, params={"content": "true"}, timeout=_timeout())
    response.raise_for_status()
    return response.json().get("jobs", [])


async def fetch_jobs_filtered_async(
    client: httpx.AsyncClient, board_token: str, title_matches: Callable[[str], bool]
) -> list[NormalizedJobPosting]:
    """Async counterpart to fetch_jobs_filtered(), used by
    ingestion/runner.py's concurrent multi-company fetch
    (_fetch_sources_concurrently). Takes an already-open `client` rather
    than opening its own -- the caller owns one shared AsyncClient across
    every company's concurrent fetch, not one per company.
    """
    raw = await _fetch_raw_async(client, board_token)
    return [_to_posting(job) for job in raw if title_matches(job["title"])]
