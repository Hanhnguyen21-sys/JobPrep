"""Tests for ingestion/readme.py -- the GitHub-README discovery source
that replaces the Greenhouse/Lever board APIs.

No live network calls: fetch_readme's httpx.get is monkeypatched where
exercised at all, and every parsing test feeds a fixture string straight
into split_sections/parse_section_table/discover_postings instead. The
fixture below mirrors real markup pulled from
SimplifyJobs/Summer2027-Internships's README.md (verified by hand against
a live fetch while building this module), not an invented shape.
"""

from unittest.mock import patch

import httpx

from app.ingestion import readme as readme_source

# Mirrors one real table: a normal row (DTCC), a company with two roles
# back-to-back where the second is a "↳" continuation row (Compeer
# Financial), and the header row every real table also has.
SOFTWARE_SECTION_HTML = """
[Back to top](#top)

<table>
<thead>
<tr>
<th>Company</th>
<th>Role</th>
<th>Location</th>
<th>Application</th>
<th>Age</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/DTCC?utm_source=GHList">DTCC</a></strong></td>
<td>Application Developer Intern</td>
<td>Tampa, FL<br>Dallas, TX<br>Jersey City, NJ</td>
<td><div align="center"><a href="https://ebxr.fa.us2.oraclecloud.com/job/214459"><img src="apply.png" alt="Apply"></a> <a href="https://simplify.jobs/p/a1eb1e2b-bd12-4ee2-b019-34e40010a803?utm_source=GHList"><img src="simplify.png" alt="Simplify"></a></div></td>
<td>0d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/Compeer-Financial?utm_source=GHList">Compeer Financial</a></strong></td>
<td>Engineering Intern</td>
<td>Sun Prairie, WI<br>Mankato, MN</td>
<td><div align="center"><a href="https://job-boards.greenhouse.io/compeerfinancial/jobs/5404850008"><img src="apply.png" alt="Apply"></a> <a href="https://simplify.jobs/p/a19e6481-79f8-4c12-b497-9d6b4566b45d?utm_source=GHList"><img src="simplify.png" alt="Simplify"></a></div></td>
<td>22d</td>
</tr>
<tr>
<td>↳</td>
<td>Engineering Intern</td>
<td>Lakeville, MN</td>
<td><div align="center"><a href="https://job-boards.greenhouse.io/compeerfinancial/jobs/5405050008"><img src="apply.png" alt="Apply"></a> <a href="https://simplify.jobs/p/4ade01ff-90f7-40e7-88aa-1756bc4d6de1?utm_source=GHList"><img src="simplify.png" alt="Simplify"></a></div></td>
<td>1mo</td>
</tr>
</tbody>
</table>
"""

FULL_README = f"""# Summer 2027 Tech Internships

Some intro text.

## \U0001f4bb Software Engineering Internship Roles
{SOFTWARE_SECTION_HTML}
## \U0001f4f1 Product Management Internship Roles

<table>
<thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th><th>Age</th></tr></thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/OtherCo?utm_source=GHList">OtherCo</a></strong></td>
<td>PM Intern</td>
<td>Remote</td>
<td><div align="center"><a href="https://jobs.lever.co/otherco/xyz"><img src="apply.png" alt="Apply"></a> <a href="https://simplify.jobs/p/11111111-1111-1111-1111-111111111111"><img src="simplify.png" alt="Simplify"></a></div></td>
<td>3d</td>
</tr>
</tbody>
</table>
"""


# ---------------------------------------------------------------------------
# split_sections
# ---------------------------------------------------------------------------


def test_split_sections_keys_by_heading_without_hashes():
    sections = readme_source.split_sections(FULL_README)
    assert "\U0001f4bb Software Engineering Internship Roles" in sections
    assert "\U0001f4f1 Product Management Internship Roles" in sections


def test_split_sections_body_stops_before_next_heading():
    sections = readme_source.split_sections(FULL_README)
    software_body = sections["\U0001f4bb Software Engineering Internship Roles"]
    assert "OtherCo" not in software_body
    assert "DTCC" in software_body


# ---------------------------------------------------------------------------
# parse_section_table
# ---------------------------------------------------------------------------


def test_parses_a_normal_row():
    postings = readme_source.parse_section_table(SOFTWARE_SECTION_HTML)
    dtcc = next(p for p in postings if p.company_name == "DTCC")

    assert dtcc.title == "Application Developer Intern"
    assert dtcc.url == "https://ebxr.fa.us2.oraclecloud.com/job/214459"
    assert dtcc.external_id == "a1eb1e2b-bd12-4ee2-b019-34e40010a803"
    assert dtcc.source_updated_at is not None


def test_continuation_row_inherits_company_from_previous_row():
    postings = readme_source.parse_section_table(SOFTWARE_SECTION_HTML)
    compeer_rows = [p for p in postings if p.company_name == "Compeer Financial"]

    assert len(compeer_rows) == 2
    # Distinct postings despite sharing a company -- different external_id.
    assert compeer_rows[0].external_id != compeer_rows[1].external_id


def test_header_row_is_not_parsed_as_a_posting():
    postings = readme_source.parse_section_table(SOFTWARE_SECTION_HTML)
    assert all(p.title != "Role" for p in postings)
    assert len(postings) == 3  # DTCC + 2 Compeer rows, not a 4th for the header


def test_empty_section_returns_no_postings():
    assert readme_source.parse_section_table("no table here") == []


# ---------------------------------------------------------------------------
# age parsing
# ---------------------------------------------------------------------------


def test_age_in_days_parses_to_a_recent_datetime():
    from datetime import datetime, timezone

    parsed = readme_source._parse_age("0d")
    assert parsed is not None
    assert (datetime.now(timezone.utc) - parsed).total_seconds() < 60


def test_age_in_months_parses_using_thirty_day_approximation():
    from datetime import datetime, timedelta, timezone

    parsed = readme_source._parse_age("1mo")
    expected = datetime.now(timezone.utc) - timedelta(days=30)
    assert parsed is not None
    assert abs((parsed - expected).total_seconds()) < 60


def test_unparseable_age_returns_none():
    assert readme_source._parse_age("unknown") is None


# ---------------------------------------------------------------------------
# discover_postings -- section filtering end to end
# ---------------------------------------------------------------------------


def test_discover_postings_only_includes_wanted_sections():
    postings = readme_source.discover_postings(readme_text=FULL_README)

    companies = {p.company_name for p in postings}
    assert companies == {"DTCC", "Compeer Financial"}
    assert "OtherCo" not in companies


def test_discover_postings_can_widen_to_additional_sections():
    postings = readme_source.discover_postings(
        section_names=(
            "Software Engineering Internship Roles",
            "Product Management Internship Roles",
        ),
        readme_text=FULL_README,
    )

    companies = {p.company_name for p in postings}
    assert companies == {"DTCC", "Compeer Financial", "OtherCo"}


# ---------------------------------------------------------------------------
# fetch_readme -- network call shape only, no real request
# ---------------------------------------------------------------------------


def test_fetch_readme_uses_configured_timeout_and_raw_url():
    response = httpx.Response(200, text=FULL_README, request=httpx.Request("GET", "https://x"))
    with patch("httpx.get", return_value=response) as mock_get:
        text = readme_source.fetch_readme()

    assert text == FULL_README
    args, kwargs = mock_get.call_args
    assert args[0] == readme_source.RAW_URL
    assert isinstance(kwargs["timeout"], httpx.Timeout)


def test_fetch_readme_raises_on_http_error():
    import pytest

    response = httpx.Response(500, text="", request=httpx.Request("GET", "https://x"))
    with patch("httpx.get", return_value=response):
        with pytest.raises(httpx.HTTPStatusError):
            readme_source.fetch_readme()
