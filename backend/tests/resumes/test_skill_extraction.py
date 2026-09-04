"""Tests for services/skill_extraction.py's structured-output contract:
`ExtractedSkill` carries `name` + a proficiency estimate
(`proficiency_level`, `proficiency_confidence`) -- not an extraction
*confidence* -- and `extract_skills()` never calls the real OpenAI API
(the client is monkeypatched, per the rest of this suite's convention).
"""

import pytest
from pydantic import ValidationError

from app.services import skill_extraction
from app.services.skill_extraction import (
    ExtractedSkill,
    SkillExtractionResult,
    extract_skills,
)


# ---------------------------------------------------------------------------
# ExtractedSkill validation
# ---------------------------------------------------------------------------


def test_valid_proficiency_output_is_accepted():
    skill = ExtractedSkill(name="Python", proficiency_level=65, proficiency_confidence="high")

    assert skill.name == "Python"
    assert skill.proficiency_level == 65
    assert skill.proficiency_confidence == "high"


@pytest.mark.parametrize("level", [-1, -50, 101, 1000])
def test_proficiency_level_rejects_out_of_range_values(level):
    with pytest.raises(ValidationError):
        ExtractedSkill(name="Python", proficiency_level=level, proficiency_confidence="high")


@pytest.mark.parametrize("level", [0, 100])
def test_proficiency_level_accepts_boundary_values(level):
    skill = ExtractedSkill(name="Python", proficiency_level=level, proficiency_confidence="low")
    assert skill.proficiency_level == level


def test_proficiency_confidence_rejects_unsupported_values():
    with pytest.raises(ValidationError):
        ExtractedSkill(name="Python", proficiency_level=50, proficiency_confidence="very-high")


def test_extracted_skill_has_no_evidence_or_reasoning_fields():
    fields = ExtractedSkill.model_fields
    assert set(fields) == {"name", "proficiency_level", "proficiency_confidence"}


# ---------------------------------------------------------------------------
# extract_skills() -- OpenAI call mocked, never hits a live API
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class _FakeChoice:
    def __init__(self, parsed):
        self.message = _FakeMessage(parsed)


class _FakeCompletion:
    def __init__(self, parsed):
        self.choices = [_FakeChoice(parsed)]


class _FakeClient:
    def __init__(self, parsed):
        self._parsed = parsed
        self.beta = self
        self.chat = self
        self.completions = self

    def parse(self, **kwargs):
        return _FakeCompletion(self._parsed)


def test_extract_skills_returns_parsed_result(monkeypatch):
    parsed = SkillExtractionResult(
        technical_skills=[
            ExtractedSkill(name="Python", proficiency_level=70, proficiency_confidence="high")
        ],
        soft_skills=[
            ExtractedSkill(name="Communication", proficiency_level=40, proficiency_confidence="medium")
        ],
    )
    monkeypatch.setattr(skill_extraction, "get_ai_client", lambda: _FakeClient(parsed))

    result = extract_skills("some resume text")

    assert result.technical_skills[0].name == "Python"
    assert result.technical_skills[0].proficiency_level == 70
    assert result.soft_skills[0].proficiency_confidence == "medium"


def test_extract_skills_returns_empty_result_when_model_refuses(monkeypatch):
    monkeypatch.setattr(skill_extraction, "get_ai_client", lambda: _FakeClient(None))

    result = extract_skills("some resume text")

    assert result.technical_skills == []
    assert result.soft_skills == []
