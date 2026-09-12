"""Tests for services/job_description_fetch.py's httpx+Trafilatura ->
Playwright fallback pipeline.

No real network call and no real browser launch is made anywhere in this
file: httpx.get is monkeypatched (same convention as
tests/ingestion/test_ats_fetch.py), and Playwright is faked out via a
stand-in `playwright.sync_api` module injected into sys.modules -- see
_install_fake_playwright below. `_fetch_via_browser`/`_fetch_via_http`
are patched directly for the tests that only care about
fetch_job_description's own two-stage sequencing.
"""

import sys
import types
from unittest.mock import MagicMock

import httpx
import pytest

from app.services import job_description_fetch as jdf

REAL_DESCRIPTION_HTML = """
<html><body><article>
<h1>Software Engineer Intern</h1>
<p>We are looking for a Software Engineer Intern to join our platform
team. You will work on backend services, write tests, and collaborate
with senior engineers on real production systems throughout the
internship.</p>
<p>Requirements: familiarity with Python, SQL, and REST APIs. Strong
communication skills and a willingness to learn are a must.</p>
</article></body></html>
"""

JS_PLACEHOLDER_HTML = """
<html><body><div id="root"></div>
<noscript>You need to enable JavaScript to run this app.</noscript>
</body></html>
"""


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------


def test_normalize_strips_application_segment_and_suffix():
    url = (
        "https://jobs.ashbyhq.com/hadrian-automation/"
        "f718bcfe-3f5b-4682-a294-697499caf813/application"
        "?embed=true&utm_source=Simplify&ref=Simplify"
    )
    assert jdf._normalize_description_url(url) == (
        "https://jobs.ashbyhq.com/hadrian-automation/"
        "f718bcfe-3f5b-4682-a294-697499caf813"
    )


def test_normalize_strips_segments_and_fragment_after_application():
    url = "https://example.com/co/123/application/confirm#top"
    assert jdf._normalize_description_url(url) == "https://example.com/co/123"


def test_normalize_preserves_url_without_application_segment():
    url = "https://boards.greenhouse.io/acme/jobs/12345"
    assert jdf._normalize_description_url(url) == url


def test_normalize_does_not_match_application_engineer_segment():
    url = "https://example.com/jobs/application-engineer/123"
    assert jdf._normalize_description_url(url) == url


def test_normalize_handles_bare_application_path():
    assert jdf._normalize_description_url("https://example.com/application") == (
        "https://example.com/"
    )


# ---------------------------------------------------------------------------
# Shared validation helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "You need to enable JavaScript to run this app.",
        "Please enable JavaScript.",
        "   Please enable JavaScript.   ",
    ],
)
def test_is_valid_description_rejects_js_placeholder_only(text):
    assert jdf._is_valid_description(text) is False


def test_is_valid_description_rejects_too_short_real_text():
    assert jdf._is_valid_description("Great team, apply now!") is False


def test_is_valid_description_rejects_empty_or_none():
    assert jdf._is_valid_description(None) is False
    assert jdf._is_valid_description("   ") is False


def test_is_valid_description_accepts_real_content_mentioning_js_notice():
    text = (
        "We are hiring a Software Engineer Intern to build backend "
        "services used by every team. Please enable JavaScript if you "
        "use our internal portal to track your application status. "
        "Requirements: Python, SQL, REST APIs, and strong communication."
    )
    assert jdf._is_valid_description(text) is True


def test_is_valid_description_accepts_real_content():
    assert jdf._is_valid_description(
        "We are looking for a Software Engineer Intern to join our "
        "platform team and work on real production systems."
    ) is True


# ---------------------------------------------------------------------------
# fetch_job_description sequencing: HTTP first, browser only as fallback
# ---------------------------------------------------------------------------


def _http_response(html: str, content_type: str = "text/html") -> httpx.Response:
    return httpx.Response(
        200,
        text=html,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://x"),
    )


def test_successful_http_extraction_does_not_invoke_browser(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _http_response(REAL_DESCRIPTION_HTML))

    def _fail_if_called(url):
        raise AssertionError("browser fallback must not run when HTTP succeeds")

    monkeypatch.setattr(jdf, "_fetch_via_browser", _fail_if_called)

    result = jdf.fetch_job_description("https://boards.greenhouse.io/acme/jobs/1")

    assert result is not None
    assert "Software Engineer Intern" in result


def test_invalid_http_content_triggers_browser_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _http_response(JS_PLACEHOLDER_HTML))

    browser_mock = MagicMock(return_value="Rendered description from the browser.")
    monkeypatch.setattr(jdf, "_fetch_via_browser", browser_mock)

    result = jdf.fetch_job_description(
        "https://jobs.ashbyhq.com/co/123/application?embed=true"
    )

    assert result == "Rendered description from the browser."
    browser_mock.assert_called_once_with("https://jobs.ashbyhq.com/co/123")


def test_http_error_triggers_browser_fallback(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))

    monkeypatch.setattr(httpx, "get", _raise)
    browser_mock = MagicMock(return_value="Rendered description from the browser.")
    monkeypatch.setattr(jdf, "_fetch_via_browser", browser_mock)

    result = jdf.fetch_job_description("https://example.com/jobs/1")

    assert result == "Rendered description from the browser."
    browser_mock.assert_called_once()


def test_both_methods_failing_returns_none(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))

    monkeypatch.setattr(httpx, "get", _raise)
    monkeypatch.setattr(jdf, "_fetch_via_browser", lambda url: None)

    assert jdf.fetch_job_description("https://example.com/jobs/1") is None


def test_missing_url_returns_none_without_any_fetch(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch"))
    )
    monkeypatch.setattr(
        jdf, "_fetch_via_browser", lambda url: (_ for _ in ()).throw(AssertionError("must not run"))
    )
    assert jdf.fetch_job_description(None) is None
    assert jdf.fetch_job_description("") is None


# ---------------------------------------------------------------------------
# Playwright fallback internals -- fake playwright.sync_api, no real browser
# ---------------------------------------------------------------------------


class _FakeTimeoutError(Exception):
    pass


class _FakePlaywrightError(Exception):
    pass


class _FakePage:
    def __init__(self, html: str, raise_on: str | None = None):
        self._html = html
        self.raise_on = raise_on
        self.closed = False
        self.goto_calls: list[str] = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self.raise_on == "goto_timeout":
            raise _FakeTimeoutError("navigation timeout")

    def wait_for_selector(self, selector, timeout=None):
        if self.raise_on == "selector_timeout":
            raise _FakeTimeoutError("selector timeout")

    def wait_for_function(self, fn, timeout=None):
        if self.raise_on == "content_wait_timeout":
            raise _FakeTimeoutError("content wait timeout")

    def content(self):
        return self._html

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, context=None, launch_error=None):
        self._context = context
        self.closed = False

    def new_context(self, user_agent=None):
        return self._context

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser=None, launch_error=None):
        self._browser = browser
        self._launch_error = launch_error

    def launch(self, headless=True):
        if self._launch_error:
            raise self._launch_error
        return self._browser


class _FakePlaywrightHandle:
    def __init__(self, chromium):
        self.chromium = chromium


class _FakeSyncPlaywrightCM:
    def __init__(self, handle):
        self._handle = handle

    def __enter__(self):
        return self._handle

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_fake_playwright(monkeypatch, *, html="", launch_error=None, raise_on=None):
    """Injects a fake `playwright.sync_api` module into sys.modules so
    `_fetch_via_browser`'s local `from playwright.sync_api import ...`
    picks up fakes instead of (or in the absence of) the real package.
    Returns the fake page/context/browser so tests can assert on
    close()/goto() calls.
    """
    page = _FakePage(html, raise_on=raise_on)
    context = _FakeContext(page)
    browser = _FakeBrowser(context=context, launch_error=launch_error)
    chromium = _FakeChromium(browser=browser, launch_error=launch_error)
    handle = _FakePlaywrightHandle(chromium)

    fake_module = types.ModuleType("playwright.sync_api")
    fake_module.sync_playwright = lambda: _FakeSyncPlaywrightCM(handle)
    fake_module.Error = _FakePlaywrightError
    fake_module.TimeoutError = _FakeTimeoutError

    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
    return page, context, browser


def test_browser_returns_valid_content_and_cleans_up(monkeypatch):
    page, context, browser = _install_fake_playwright(monkeypatch, html=REAL_DESCRIPTION_HTML)

    result = jdf._fetch_via_browser("https://jobs.ashbyhq.com/co/123")

    assert result is not None
    assert "Software Engineer Intern" in result
    assert page.goto_calls == ["https://jobs.ashbyhq.com/co/123"]
    assert page.closed is True
    assert context.closed is True
    assert browser.closed is True


def test_browser_rejects_placeholder_content(monkeypatch):
    _install_fake_playwright(monkeypatch, html=JS_PLACEHOLDER_HTML)

    assert jdf._fetch_via_browser("https://jobs.ashbyhq.com/co/123") is None


def test_browser_navigation_timeout_returns_none_and_cleans_up(monkeypatch):
    page, context, browser = _install_fake_playwright(
        monkeypatch, html=REAL_DESCRIPTION_HTML, raise_on="goto_timeout"
    )

    assert jdf._fetch_via_browser("https://example.com/co/123") is None
    # goto() raised before content() was ever read, but cleanup must still
    # run for both the context and the browser.
    assert context.closed is True
    assert browser.closed is True


def test_browser_falls_back_past_missing_selector_to_content_wait(monkeypatch):
    """No known ATS selector matches, but the generic content-wait still
    lets extraction proceed once page.content() is read -- selector
    timeout alone must not be treated as a fatal failure.
    """
    page, _, _ = _install_fake_playwright(
        monkeypatch, html=REAL_DESCRIPTION_HTML, raise_on="selector_timeout"
    )

    result = jdf._fetch_via_browser("https://example.com/co/123")

    assert result is not None
    assert "Software Engineer Intern" in result


def test_browser_unavailable_when_playwright_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    assert jdf._fetch_via_browser("https://example.com/co/123") is None


def test_browser_launch_failure_returns_none(monkeypatch):
    _install_fake_playwright(
        monkeypatch, launch_error=_FakePlaywrightError("Executable doesn't exist at ...")
    )

    assert jdf._fetch_via_browser("https://example.com/co/123") is None
