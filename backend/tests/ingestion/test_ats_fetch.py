"""Tests for Phase 1 items 1 (filter titles before HTML-stripping) and 2
(explicit ATS timeouts) in ingestion/greenhouse.py and ingestion/lever.py.

httpx.get is monkeypatched throughout -- no real network call is made.
"""

from unittest.mock import MagicMock, patch

import httpx

from app.ingestion import greenhouse, lever


def _greenhouse_response(titles: list[str]) -> httpx.Response:
    jobs = [
        {
            "id": i,
            "title": title,
            "location": {"name": "Remote"},
            "content": f"<p>Description for {title}</p>",
            "absolute_url": f"https://example.com/{i}",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        for i, title in enumerate(titles)
    ]
    return httpx.Response(200, json={"jobs": jobs}, request=httpx.Request("GET", "https://x"))


def _lever_response(titles: list[str]) -> httpx.Response:
    postings = [
        {
            "id": str(i),
            "text": title,
            "categories": {"location": "Remote"},
            "descriptionPlain": f"Description for {title}",
            "hostedUrl": f"https://example.com/{i}",
            "createdAt": 1700000000000,
        }
        for i, title in enumerate(titles)
    ]
    return httpx.Response(200, json=postings, request=httpx.Request("GET", "https://x"))


# ---------------------------------------------------------------------------
# Item 1: HTML stripping only for matching postings (Greenhouse)
# ---------------------------------------------------------------------------


def test_fetch_jobs_filtered_only_strips_html_for_matching_titles():
    titles = ["Software Engineer", "Product Designer", "Software Engineer II", "Recruiter"]
    strip_calls = []
    real_strip = greenhouse._strip_html

    def counting_strip(html):
        strip_calls.append(html)
        return real_strip(html)

    with patch("httpx.get", return_value=_greenhouse_response(titles)), patch(
        "app.ingestion.greenhouse._strip_html", counting_strip
    ):
        matched = greenhouse.fetch_jobs_filtered(
            "acme", lambda title: "software engineer" in title.lower()
        )

    assert len(matched) == 2
    assert {p.title for p in matched} == {"Software Engineer", "Software Engineer II"}
    # Only the 2 matching postings' descriptions were ever passed to
    # _strip_html -- not all 4 fetched postings.
    assert len(strip_calls) == 2


def test_fetch_jobs_unfiltered_still_strips_every_posting():
    """fetch_jobs() (the broad/run_ingestion path) is unchanged -- it
    needs every posting's description regardless of any search term.
    """
    titles = ["Software Engineer", "Product Designer", "Recruiter"]
    strip_calls = []
    real_strip = greenhouse._strip_html

    def counting_strip(html):
        strip_calls.append(html)
        return real_strip(html)

    with patch("httpx.get", return_value=_greenhouse_response(titles)), patch(
        "app.ingestion.greenhouse._strip_html", counting_strip
    ):
        postings = greenhouse.fetch_jobs("acme")

    assert len(postings) == 3
    assert len(strip_calls) == 3


def test_lever_fetch_jobs_filtered_only_constructs_matching_postings():
    titles = ["Software Engineer", "Product Designer", "Software Engineer II"]
    with patch("httpx.get", return_value=_lever_response(titles)):
        matched = lever.fetch_jobs_filtered(
            "acme", lambda title: "software engineer" in title.lower()
        )
    assert len(matched) == 2


# ---------------------------------------------------------------------------
# Item 2: explicit ATS timeouts
# ---------------------------------------------------------------------------


def test_greenhouse_fetch_uses_configured_timeout():
    with patch("httpx.get", return_value=_greenhouse_response([])) as mock_get:
        greenhouse.fetch_jobs("acme")

    _, kwargs = mock_get.call_args
    timeout = kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    from app.core.config import get_settings

    settings = get_settings()
    assert timeout.connect == settings.ats_connect_timeout_seconds
    assert timeout.read == settings.ats_read_timeout_seconds


def test_lever_fetch_uses_configured_timeout():
    with patch("httpx.get", return_value=_lever_response([])) as mock_get:
        lever.fetch_jobs("acme")

    _, kwargs = mock_get.call_args
    timeout = kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)


def test_ats_read_timeout_raises_httpx_timeout_error():
    """A slow/unresponsive ATS should raise httpx's own timeout error
    (not hang indefinitely) -- exercised here via httpx.get raising
    directly, since we don't want a real slow socket in the test suite.
    """
    import pytest

    with patch("httpx.get", side_effect=httpx.ReadTimeout("simulated slow ATS")):
        with pytest.raises(httpx.ReadTimeout):
            greenhouse.fetch_jobs("acme")
