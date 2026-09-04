

import httpx
import trafilatura

from app.core.config import get_settings

# Below this many non-whitespace characters, treat the extraction as
# "didn't really get the description" rather than persisting a near-empty
# string -- same reasoning as services/resume_ocr.py's MIN_TEXT_LENGTH.
MIN_TEXT_LENGTH = 40

# Bounds how much HTML we hand to Trafilatura for one posting -- same
# "bound the worst case" reasoning as api/routes/resumes.py's
# MAX_FILE_BYTES, applied to a page someone else's server returns instead
# of a file a user uploads.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# Some ATS/career pages block requests with no User-Agent (or a
# library-default one) outright -- a generic browser-like UA avoids that
# trivial block without pretending to be a specific real browser/version.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobPrepBot/1.0)"}


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.ats_connect_timeout_seconds,
        read=settings.ats_read_timeout_seconds,
        write=settings.ats_read_timeout_seconds,
        pool=settings.ats_connect_timeout_seconds,
    )


def fetch_job_description(url: str | None) -> str | None:
    """Fetch `url` and return its extracted main-content text, or None if
    anything about that failed (bad/missing url, network error, non-HTML
    response, too-large response, or nothing extractable -- e.g. a
    JS-rendered SPA page that returns near-empty HTML over plain HTTP).
    Never raises -- see module docstring.
    """
    if not url:
        return None

    try:
        response = httpx.get(
            url, timeout=_timeout(), follow_redirects=True, headers=_HEADERS
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    content_type = response.headers.get("content-type", "")
    if not any(allowed in content_type for allowed in _ALLOWED_CONTENT_TYPES):
        return None

    if len(response.content) > MAX_RESPONSE_BYTES:
        return None

    try:
        extracted = trafilatura.extract(
            response.text, include_comments=False, include_tables=False
        )
    except Exception:
        # Trafilatura isn't guaranteed exception-free on every malformed
        # real-world page (bad encoding, parser edge cases) -- one bad
        # posting's page must not be able to raise past this function,
        # per the module docstring's "never raises" contract.
        return None
    if extracted is None:
        return None

    extracted = extracted.strip()
    if len(extracted) < MIN_TEXT_LENGTH:
        return None

    return extracted
