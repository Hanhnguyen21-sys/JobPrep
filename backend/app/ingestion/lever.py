"""Lever Postings API client.

Public, unauthenticated endpoint -- no API key needed. Docs:
https://github.com/lever/postings-api

Returns NormalizedJobPosting, the same shape greenhouse.py returns, so
ingestion/runner.py doesn't need to know which ATS a posting came from.
"""

from datetime import datetime, timezone

import httpx

from app.ingestion.common import NormalizedJobPosting

BASE_URL = "https://api.lever.co/v0/postings"


def fetch_jobs(site: str) -> list[NormalizedJobPosting]:
    """Fetch every open posting for one Lever site."""
    url = f"{BASE_URL}/{site}"
    response = httpx.get(url, params={"mode": "json"}, timeout=15.0)
    response.raise_for_status()

    postings = []
    for posting in response.json():
        postings.append(
            NormalizedJobPosting(
                external_id=posting["id"],
                title=posting["text"],
                location=(posting.get("categories") or {}).get("location"),
                description=posting.get("descriptionPlain") or None,
                url=posting.get("hostedUrl"),
                source_updated_at=_parse_epoch_ms(posting.get("createdAt")),
            )
        )
    return postings


def _parse_epoch_ms(value: int | None) -> datetime | None:
    """Lever gives `createdAt` in epoch milliseconds and doesn't expose a
    separate "last updated" timestamp -- see module docstring caveat.
    """
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
