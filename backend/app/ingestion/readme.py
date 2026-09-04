
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


DEFAULT_SECTION_NAMES: tuple[str, ...] = ("Software Engineering Internship Roles",
                                          "Product Management Internship Roles",
                                          "Data Science, AI & Machine Learning Internship Roles",
                                          "Quantitative Finance Internship Roles",
                                          "Hardware Engineering Internship Roles")

# Only postings strictly older than this (in whole days, per the source's
# own coarse age label) are kept -- filters out just-listed rows. Compared
# against the parsed day-count directly (see _parse_age_days), not by
# re-deriving elapsed wall-clock time from source_updated_at with a second
# datetime.now() call, which would make a borderline "7d" posting flicker
# across the threshold depending on exactly when it's checked.
MIN_POSTING_AGE_DAYS = 7


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


def _parse_age_days(text: str) -> int | None:
    """convert date in text format to integer
    """
    match = _AGE_RE.search(text.strip())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    return amount * 30 if unit == "mo" else amount


def _parse_age(text: str) -> datetime | None:
    """convert age in string format to datetime
    """
    days = _parse_age_days(text)
    if days is None:
        return None
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
    # cells[2] is location col -> skip it since the project does not use location
    apply_url, external_id = _application_from_cell(cells[3])
    age_text = cells[4].get_text()
    # convert age_text ("4d") to datetime
    source_updated_at = _parse_age(age_text)

    if not title or external_id is None:
        # No stable id to key off of -- skip rather than upsert something
        # we can't reliably de-dupe/update on a later run.
        return None, company_name

    age_days = _parse_age_days(age_text)
    if age_days is None or age_days <= MIN_POSTING_AGE_DAYS:
        # Unknown age, or not yet older than MIN_POSTING_AGE_DAYS -- skip.
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
   
    text = readme_text if readme_text is not None else fetch_readme()
    sections = split_sections(text)

    postings: list[DiscoveredPosting] = []
    for heading, body in sections.items():
        if _matches_section(heading, section_names):
            postings.extend(parse_section_table(body))
    return postings


