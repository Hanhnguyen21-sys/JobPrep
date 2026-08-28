
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import get_settings

RAW_URL = (
    "https://raw.githubusercontent.com/"
    "SimplifyJobs/Summer2027-Internships/refs/heads/dev/README.md"
)

# Section headings are emoji-prefixed ("## \U0001f4bb Software Engineering
# Internship Roles") -- matched by suffix rather than exact string so an
# emoji change upstream doesn't silently break discovery. Add more entries
# here to widen discovery to other categories (Product, Data Science, ...),
# same pattern ingestion/runner.py's old DEFAULT_COMPANIES list used for
# "add another source by adding a list entry."
DEFAULT_SECTION_NAMES: tuple[str, ...] = ("Software Engineering Internship Roles",)


@dataclass(frozen=True)
class DiscoveredPosting:
   

    external_id: str
    company_name: str
    title: str
    url: str | None
    source_updated_at: datetime | None


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.ats_connect_timeout_seconds,
        read=settings.ats_read_timeout_seconds,
        write=settings.ats_read_timeout_seconds,
        pool=settings.ats_connect_timeout_seconds,
    )


def fetch_readme(url: str = RAW_URL) -> str:
    """Fetch the raw README.md text. Public, unauthenticated --
    raw.githubusercontent.com needs no token and isn't subject to the
    much lower api.github.com unauthenticated rate limit.
    """
    response = httpx.get(url, timeout=_timeout())
    response.raise_for_status()
    return response.text


def split_sections(md_text: str) -> dict[str, str]:
    """Splits on top-level "## " headings into {heading: body_text}.
    Adapted from the reference implementation this module is based on --
    unchanged behavior, just typed/docstringed to this repo's convention.
    """
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(md_text))
    sections: dict[str, str] = {}

    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md_text)
        sections[title] = md_text[start:end]

    return sections


def _matches_section(heading: str, wanted: tuple[str, ...]) -> bool:
    return any(heading.strip().endswith(name) for name in wanted)


_SIMPLIFY_POSTING_RE = re.compile(r"simplify\.jobs/p/([0-9a-fA-F-]{36})")
_AGE_RE = re.compile(r"(\d+)\s*(d|mo)\b")


def _company_from_cell(cell: Tag, carry: str | None) -> str | None:
   
    link = cell.find("a")
    if link is None:
        return carry

    return link.get_text(strip=True)


def _application_from_cell(cell: Tag) -> tuple[str | None, str | None]:
    
    apply_url: str | None = None
    external_id: str | None = None

    for link in cell.find_all("a"):
        href = link.get("href", "")
        posting_match = _SIMPLIFY_POSTING_RE.search(href)
        if posting_match:
            external_id = posting_match.group(1)
        elif apply_url is None:
            apply_url = href or None

    return apply_url, external_id


def _parse_age(text: str) -> datetime | None:
    """Age is a coarse, day-or-month-granularity relative string ("0d",
    "22d", "1mo") -- best-effort only, never trusted the way Lever's
    createdAt/Greenhouse's updated_at are (see ingestion/lever.py's
    docstring on the same caveat). Returns None on anything that doesn't
    parse rather than guessing; "mo" is approximated as 30 days.
    """
    match = _AGE_RE.search(text.strip())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    days = amount * 30 if unit == "mo" else amount
    return datetime.now(timezone.utc) - timedelta(days=days)


def _parse_row(
    row: Tag, carry: str | None
) -> tuple[DiscoveredPosting | None, str | None]:
    cells = row.find_all("td")
    if len(cells) < 5:
        return None, carry  # header row (<th>) or malformed -- skip

    company_name = _company_from_cell(cells[0], carry)
    if company_name is None:
        return None, carry

    title = cells[1].get_text(strip=True)
    apply_url, external_id = _application_from_cell(cells[3])
    source_updated_at = _parse_age(cells[4].get_text())

    if not title or external_id is None:
        # No stable id to key off of -- skip rather than upsert something
        # we can't reliably de-dupe/update on a later run.
        return None, company_name

    posting = DiscoveredPosting(
        external_id=external_id,
        company_name=company_name,
        title=title,
        url=apply_url,
        source_updated_at=source_updated_at,
    )
    return posting, company_name


def parse_section_table(section_html: str) -> list[DiscoveredPosting]:
    """Parses the one HTML <table> embedded in a README section into
    DiscoveredPosting objects. Company identity carries forward across
    "↳" continuation rows within this table only -- each call starts
    fresh, so a company split across two different sections never gets
    merged.
    """
    soup = BeautifulSoup(section_html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    body = table.find("tbody") or table
    postings: list[DiscoveredPosting] = []
    carry: str | None = None

    for row in body.find_all("tr"):
        posting, carry = _parse_row(row, carry)
        if posting is not None:
            postings.append(posting)

    return postings


def discover_postings(
    section_names: tuple[str, ...] = DEFAULT_SECTION_NAMES,
    readme_text: str | None = None,
) -> list[DiscoveredPosting]:
    """Entry point: fetch (unless `readme_text` is given -- tests pass a
    fixture this way instead of hitting the network) + split + parse every
    wanted section into one flat list. Section order follows
    `section_names`; within a section, README order is preserved.
    """
    text = readme_text if readme_text is not None else fetch_readme()
    sections = split_sections(text)

    postings: list[DiscoveredPosting] = []
    for heading, body in sections.items():
        if _matches_section(heading, section_names):
            postings.extend(parse_section_table(body))
    return postings


