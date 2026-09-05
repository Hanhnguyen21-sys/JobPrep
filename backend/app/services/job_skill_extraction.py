"""Job-posting skill extraction: match an already-clean job description
against the ESCO taxonomy (app/taxonomy) with a spaCy PhraseMatcher.

No LLM, no network on this path -- the description handed in here is the
main-content text Trafilatura pulled out of the posting's HTML
(`services/job_description_fetch.py::fetch_job_description` for the live
URL path, or `extract_job_skills_from_html` below for a raw HTML string).

Public contract is unchanged from the old OpenAI version: same
`ExtractedJobSkill` / `JobSkillExtractionResult` shapes and the same
`extract_job_skills` / `extract_job_skills_batch` entry points, so
`ingestion/runner.py` and its error isolation don't change.
"""

import re
from typing import Literal

import trafilatura
from pydantic import BaseModel

from app.taxonomy.matcher import SkillMatcher, get_skill_matcher


class ExtractedJobSkill(BaseModel):
    skill: str
    # Kept for schema stability; job-posting skills are all recorded as
    # "technical" (the taxonomy carries no category and runner.py hardcodes
    # it at get_or_create_skill anyway).
    category: Literal["technical", "soft"]
    evidence: str


class JobSkillExtractionResult(BaseModel):
    required_skills: list[ExtractedJobSkill]
    preferred_skills: list[ExtractedJobSkill]


# --------------------------------------------------------------------------
# required vs preferred -- section-heading heuristic
# --------------------------------------------------------------------------

# A short line matching one of these switches which bucket subsequent
# skill mentions land in. Preferred is checked first so "Preferred
# Qualifications" doesn't get caught by the generic "qualification" in the
# required set.
_PREFERRED_CUE = re.compile(
    r"nice[\s-]?to[\s-]?have|preferred qualification|preferred skill|"
    r"\bbonus\b|\bpluses\b|\ba plus\b|good[\s-]?to[\s-]?have|desirable|"
    r"would be a plus|not required but|even better",
    re.IGNORECASE,
)
_REQUIRED_CUE = re.compile(
    r"requirement|\brequired\b|must[\s-]?have|minimum qualification|"
    r"basic qualification|what you.?ll need|responsibilit|qualification|"
    r"who you are|about you|what we.?re looking for",
    re.IGNORECASE,
)
_MAX_HEADING_LEN = 80


def _preferred_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges sitting under a 'nice to have' / 'preferred' style
    heading, up to the next requirements-style heading (or end of text).
    Empty when the posting never separates the two -- callers then treat
    every skill as required, the same fallback the old LLM prompt used.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    start: int | None = None
    for line in text.splitlines(keepends=True):
        head = line.strip()
        short = 0 < len(head) <= _MAX_HEADING_LEN
        if short and _PREFERRED_CUE.search(head):
            if start is None:
                start = pos
        elif short and start is not None and _REQUIRED_CUE.search(head):
            ranges.append((start, pos))
            start = None
        pos += len(line)
    if start is not None:
        ranges.append((start, pos))
    return ranges


def _in_ranges(offset: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= offset < hi for lo, hi in ranges)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def _extract_one(matcher: SkillMatcher, description: str) -> JobSkillExtractionResult:
    text = description or ""
    pref_ranges = _preferred_ranges(text)

    required: list[ExtractedJobSkill] = []
    preferred: list[ExtractedJobSkill] = []
    for hit in matcher.extract(text):
        skill = ExtractedJobSkill(
            skill=hit.name, category="technical", evidence=hit.evidence
        )
        # Preferred only when EVERY mention of the skill sits inside a
        # preferred section -- one mention in the main requirements makes
        # it required (stricter wins, matching the old prompt).
        in_preferred = bool(pref_ranges) and all(
            _in_ranges(off, pref_ranges) for off in hit.offsets
        )
        (preferred if in_preferred else required).append(skill)

    return JobSkillExtractionResult(
        required_skills=required, preferred_skills=preferred
    )


def extract_job_skills_batch(descriptions: list[str]) -> list[JobSkillExtractionResult]:
    """Match each already-clean job description against the ESCO taxonomy.
    Kept as a "batch" call for the existing callers; with no API behind it
    this is just a map. The matcher is built once per process
    (`get_skill_matcher()` is cached).
    """
    if not descriptions:
        return []
    matcher = get_skill_matcher()
    return [_extract_one(matcher, description) for description in descriptions]


def extract_job_skills(description: str) -> JobSkillExtractionResult:
    """Single-posting convenience wrapper around extract_job_skills_batch."""
    return extract_job_skills_batch([description])[0]


def extract_job_skills_from_html(html: str) -> JobSkillExtractionResult:
    """Start from a raw HTML string / file instead of a URL: run
    Trafilatura to get the clean main-content text (same options as
    job_description_fetch.py's URL path), then match it. Use this for a
    saved .html posting or an HTML payload obtained outside the live
    ingestion flow; `fetch_job_description` stays the entry point for URLs.
    """
    text = trafilatura.extract(
        html or "", include_comments=False, include_tables=False
    )
    if not text:
        return JobSkillExtractionResult(required_skills=[], preferred_skills=[])
    return _extract_one(get_skill_matcher(), text)
