"""Greenhouse Job Board API client.

Public, unauthenticated endpoint -- no API key needed to list a company's
postings. Docs: https://developers.greenhouse.io/job-board.html

Returns NormalizedJobPosting so ingestion/runner.py doesn't need to know
this data came from Greenhouse specifically -- lever.py returns the same
shape from a completely different response format.
"""

from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.ingestion.common import NormalizedJobPosting

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


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


def fetch_jobs(board_token: str) -> list[NormalizedJobPosting]:
    """Fetch every open posting for one Greenhouse board."""
    url = f"{BASE_URL}/{board_token}/jobs"
    response = httpx.get(url, params={"content": "true"}, timeout=15.0)
    response.raise_for_status()

    postings = []
    for job in response.json().get("jobs", []):
        postings.append(
            NormalizedJobPosting(
                external_id=str(job["id"]),
                title=job["title"],
                location=(job.get("location") or {}).get("name"),
                description=_strip_html(job.get("content")),
                url=job.get("absolute_url"),
                source_updated_at=_parse_datetime(job.get("updated_at")),
            )
        )
    return postings
