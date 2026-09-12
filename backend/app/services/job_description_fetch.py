"""Fetches a job posting's description from its apply URL.

Two-stage pipeline:
  1. httpx + Trafilatura against the raw HTML (`_fetch_via_http`) -- fast,
     no browser, handles any normal server-rendered page.
  2. Playwright/headless Chromium against the same URL (`_fetch_via_browser`),
     tried only when (1) fails or returns something that isn't a real
     description (empty, too short, or a JS-required placeholder page) --
     handles JS-rendered ATS pages (Ashby, some Workday embeds) that (1)
     can never see since it never executes JavaScript.

`_normalize_description_url` strips a trailing "/application" apply-form
segment (and everything after it -- further segments, query, fragment)
off the URL before either stage fetches it, e.g. Ashby's
".../<id>/application?embed=true&..." -> ".../<id>" -- the "/application"
route is the apply form (often just a JS shell with no description
content at all), while the base posting URL one segment up usually has
the real description. This is fetch-time only: `JobPosting.url`/apply_url
in the DB is never rewritten, so posting identity/dedup (keyed on the
ATS's own external_id -- see ingestion/runner.py) is unaffected.

Both stages funnel their extracted text through `_is_valid_description`
(shared by both, via `_extract_from_html`) so "did this attempt actually
get a real description" means the same thing everywhere.

Setup: the browser fallback needs Chromium installed for Playwright --
after `pip install -r requirements.txt`, also run once per environment
(dev machine or deployment image):

    python -m playwright install chromium

Playwright's headless Chromium also needs a handful of OS-level shared
libraries (libnss3, libatk-bridge2.0-0, libgbm1, etc.) that aren't
pulled in by pip -- on a minimal Linux deployment image (e.g. a slim
Docker base), additionally run:

    python -m playwright install-deps chromium

If Chromium isn't installed, `fetch_job_description` logs an actionable
message and falls back to httpx-only behavior (returns whatever the HTTP
stage got, `None` if that also failed) rather than raising.
"""

import re
import threading
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

import httpx
import trafilatura

from app.core.config import get_settings

# Below this many *non-whitespace* characters, treat the extraction as
# "didn't really get a description" -- same reasoning as
# services/resume_ocr.py's MIN_TEXT_LENGTH. Counted on non-whitespace
# characters specifically (not raw string length) so a short real
# sentence padded with lots of blank lines by a sloppy extraction isn't
# judged more favorably than its actual content warrants.
MIN_TEXT_LENGTH = 40

# Bounds how much HTML we hand to Trafilatura / keep in memory for one
# posting. NOTE: httpx.get() has already downloaded the full response
# body by the time this check runs -- this does not stop an oversized
# response from being downloaded over the wire, only from being processed
# afterward. Real download-size protection would need a streaming
# response with an early abort once the byte cap is crossed.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# Some ATS/career pages block requests with no User-Agent (or a
# library-default one) outright -- a generic browser-like UA avoids that
# trivial block without pretending to be a specific real browser/version.
# Shared by both the HTTP and browser fetch paths so they present the
# same identity.
_USER_AGENT = "Mozilla/5.0 (compatible; JobPrepBot/1.0)"
_HEADERS = {"User-Agent": _USER_AGENT}

# ATS apply-form routes are frequently a JS shell over the *actual*
# posting page one path segment up (e.g. Ashby: ".../<id>/application" is
# the apply form; ".../<id>" is the description) -- stripped for fetching
# only, see _normalize_description_url. Matched as an exact path segment,
# never a substring, so "/application-engineer" is untouched.
_APPLICATION_SEGMENT = "application"

# Phrases a JS-required "please enable JavaScript" placeholder page uses
# instead of any real description content. Matched case-insensitively;
# used by _is_valid_description to tell a placeholder-only response apart
# from a real description that merely *mentions* JavaScript in passing
# (e.g. "familiarity with JavaScript required").
_JS_PLACEHOLDER_PATTERNS = [
    re.compile(r"you (?:need|must|have) to enable javascript", re.IGNORECASE),
    re.compile(r"please enable javascript", re.IGNORECASE),
    re.compile(r"enable javascript to (?:run|view|use|continue)", re.IGNORECASE),
    re.compile(r"javascript is (?:disabled|required|not enabled)", re.IGNORECASE),
    re.compile(r"this (?:app|page|site) (?:requires|needs) javascript", re.IGNORECASE),
]

# ATS-specific containers known to hold the actual description, tried
# before falling back to generic landmarks. A single CSS selector list
# (comma-separated is an OR in CSS) so one bounded wait covers all of
# them at once instead of a serial per-selector timeout.
_JOB_CONTENT_SELECTORS = ", ".join(
    [
        "[data-automation-id='jobPostingDescription']",  # Workday
        "div[class*='job-post' i]",  # Greenhouse and similar
        "div[class*='posting-description' i]",  # Ashby / Lever-style
        "article",
        "main",
    ]
)


def _non_whitespace_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _is_valid_description(text: str | None) -> bool:
    """Shared validation for both extraction paths: reject empty/too-short
    content and JS-required-placeholder pages. A placeholder phrase alone
    doesn't disqualify text that has substantial *other* content around
    it (e.g. a real description that happens to mention "requires
    JavaScript" as a skill) -- only text that's still too short once every
    known placeholder phrase is stripped out counts as placeholder-only.
    """
    if not text:
        return False

    stripped = text.strip()
    if _non_whitespace_len(stripped) < MIN_TEXT_LENGTH:
        return False

    residual = stripped
    for pattern in _JS_PLACEHOLDER_PATTERNS:
        residual = pattern.sub(" ", residual)

    return _non_whitespace_len(residual) >= MIN_TEXT_LENGTH


def _normalize_description_url(url: str) -> str:
    """Strip a trailing "/application" apply-form segment -- and
    everything after it, including further path segments, query, and
    fragment -- from `url`. Matches an exact path segment via
    urllib.parse, so "/application-engineer" is left untouched. Returns
    `url` unchanged if it has no such segment.

    Fetching only -- never changes what's persisted as JobPosting.url.

    Example:
        https://jobs.ashbyhq.com/co/<id>/application?embed=true&ref=x
        -> https://jobs.ashbyhq.com/co/<id>
    """
    parsed = urlparse(url)
    segments = parsed.path.split("/")
    if _APPLICATION_SEGMENT not in segments:
        return url

    index = segments.index(_APPLICATION_SEGMENT)
    new_path = "/".join(segments[:index]) or "/"
    return urlunparse((parsed.scheme, parsed.netloc, new_path, "", "", ""))


def _log_url(url: str) -> str:
    """URL with query/fragment stripped, safe to put in a log line --
    apply URLs routinely carry tracking params (utm_source, ref, ...)
    that shouldn't end up in logs.
    """
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.ats_connect_timeout_seconds,
        read=settings.ats_read_timeout_seconds,
        write=settings.ats_read_timeout_seconds,
        pool=settings.ats_connect_timeout_seconds,
    )


def _extract_from_html(html: str) -> str | None:
    """Trafilatura extraction + the shared validity check -- used by both
    the HTTP path (raw response body) and the browser path (rendered
    page.content()). Returns None on any failure or invalid content;
    callers just check for None, never see a Trafilatura exception.
    """
    try:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    except Exception:
        # Trafilatura isn't guaranteed exception-free on every malformed
        # real-world page (bad encoding, parser edge cases) -- one bad
        # posting's page must not be able to raise past this function.
        return None

    if extracted is None:
        return None

    extracted = extracted.strip()
    return extracted if _is_valid_description(extracted) else None


def _fetch_via_http(url: str) -> str | None:
    """Stage 1: plain HTTP GET + Trafilatura. Never raises -- returns
    None for any failure (network error, non-HTML response, too-large
    response, or nothing extractable/valid).
    """
    logged_url = _log_url(url)

    try:
        response = httpx.get(url, timeout=_timeout(), follow_redirects=True, headers=_HEADERS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[job_description_fetch] http failed for {logged_url}: {type(exc).__name__}")
        return None

    content_type = response.headers.get("content-type", "")
    if not any(allowed in content_type for allowed in _ALLOWED_CONTENT_TYPES):
        print(
            f"[job_description_fetch] http skipped for {logged_url}: "
            f"content-type={content_type!r}"
        )
        return None

    if len(response.content) > MAX_RESPONSE_BYTES:
        print(f"[job_description_fetch] http response too large for {logged_url}")
        return None

    extracted = _extract_from_html(response.text)
    if extracted is None:
        print(f"[job_description_fetch] http content invalid/placeholder for {logged_url}")
    return extracted


@lru_cache
def _browser_semaphore() -> threading.Semaphore:
    return threading.Semaphore(get_settings().job_description_browser_max_concurrency)


def _fetch_via_browser(url: str) -> str | None:
    """Stage 2: render `url` in headless Chromium and extract from the
    rendered HTML. Never raises -- returns None for any failure
    (Playwright/Chromium not installed, navigation timeout, or nothing
    extractable/valid once rendered).

    Uses Playwright's *sync* API deliberately: every caller in this
    codebase reaches this function from synchronous code (the roadmap
    generation background task runs via FastAPI's BackgroundTasks, which
    executes a sync def in a plain worker thread, not on the asyncio event
    loop -- see api/routes/roadmaps.py's _run_roadmap_generation_task).
    Each call opens its own `sync_playwright()` context and never shares
    a Playwright/Browser/Page object across threads, so concurrent calls
    from concurrent background tasks (each in their own worker thread)
    are safe -- only the number of simultaneously *open* browsers is
    bounded, via `_browser_semaphore()`.
    """
    try:
        from playwright.sync_api import (
            Error as PlaywrightError,
            TimeoutError as PlaywrightTimeoutError,
            sync_playwright,
        )
    except ModuleNotFoundError:
        print(
            "[job_description_fetch] browser fallback unavailable -- the "
            "`playwright` package isn't installed. Run `pip install -r "
            "requirements.txt`, then `python -m playwright install "
            "chromium` to download the browser binary itself."
        )
        return None

    settings = get_settings()
    timeout_ms = settings.job_description_browser_timeout_seconds * 1000
    logged_url = _log_url(url)
    html: str | None = None

    with _browser_semaphore():
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(user_agent=_USER_AGENT)
                    try:
                        page = context.new_page()
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                            try:
                                page.wait_for_selector(_JOB_CONTENT_SELECTORS, timeout=timeout_ms)
                            except PlaywrightTimeoutError:
                                # None of the known ATS containers showed up
                                # -- fall back to a generic "did *something*
                                # substantial render" wait rather than
                                # giving up immediately; a page we have no
                                # selector for yet can still have real
                                # content.
                                try:
                                    page.wait_for_function(
                                        "document.body && "
                                        "document.body.innerText.trim().length > 200",
                                        timeout=timeout_ms,
                                    )
                                except PlaywrightTimeoutError:
                                    pass

                            html = page.content()
                        finally:
                            page.close()
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[job_description_fetch] browser navigation timed out for {logged_url}")
            return None
        except PlaywrightError as exc:
            message = str(exc)
            if "executable doesn't exist" in message.lower():
                print(
                    "[job_description_fetch] Chromium isn't installed for "
                    "Playwright -- run `python -m playwright install "
                    "chromium` and retry."
                )
            else:
                print(
                    f"[job_description_fetch] browser error for {logged_url}: "
                    f"{type(exc).__name__}"
                )
            return None
        except Exception as exc:
            # Never let one bad page crash a roadmap generation -- same
            # "never raises" contract as the HTTP path.
            print(
                f"[job_description_fetch] browser unexpected error for {logged_url}: "
                f"{type(exc).__name__}"
            )
            return None

    extracted = _extract_from_html(html) if html else None
    if extracted is None:
        print(f"[job_description_fetch] browser content invalid/placeholder for {logged_url}")
    return extracted


def fetch_job_description(url: str | None) -> str | None:
    """Fetch `url` (an apply URL) and return its main-content job
    description text, or None if nothing usable could be extracted
    either way. Never raises.

    Tries plain HTTP + Trafilatura first (fast, no browser); only falls
    back to rendering the page in headless Chromium if that fails or
    yields something that isn't a real description (too short, or a
    JS-required placeholder). `url` is normalized (see
    _normalize_description_url) before either attempt.
    """
    if not url:
        return None

    normalized = _normalize_description_url(url)
    logged_url = _log_url(normalized)

    extracted = _fetch_via_http(normalized)
    if extracted is not None:
        print(f"[job_description_fetch] resolved via http for {logged_url}")
        return extracted

    extracted = _fetch_via_browser(normalized)
    if extracted is not None:
        print(f"[job_description_fetch] resolved via browser for {logged_url}")
        return extracted

    print(f"[job_description_fetch] no description extracted for {logged_url}")
    return None
