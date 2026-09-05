"""Tests for services/roadmap.py's current_level/target_level range
validation (Fix 2 of the roadmap skill-gap audit): both fields were
documented as "0-100" in prompt text only, with no schema enforcement, so
an out-of-range value from the model (e.g. target_level: 150) would have
flowed unvalidated through create_roadmap into the DB and the API
response.
"""

import json

import pytest
from pydantic import ValidationError

from app.services.roadmap import PrioritySkillResult, RoadmapGenerationResult


def test_priority_skill_accepts_boundary_values():
    PrioritySkillResult(skill="Python", current_level=0, target_level=100)
    PrioritySkillResult(skill="Python", current_level=100, target_level=0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_level", -1),
        ("current_level", 101),
        ("target_level", -1),
        ("target_level", 150),
    ],
)
def test_priority_skill_rejects_out_of_range_values(field, value):
    kwargs = {"skill": "Python", "current_level": 50, "target_level": 50, field: value}
    with pytest.raises(ValidationError):
        PrioritySkillResult(**kwargs)


def test_roadmap_generation_result_rejects_out_of_range_via_json_parse():
    """This is the exact call path the OpenAI SDK's `.parse()` uses to
    turn a model response into RoadmapGenerationResult (openai/lib/
    _parsing/_completions.py::_parse_content -> model_parse_json, i.e.
    pydantic's model_validate_json) -- confirms an out-of-range
    target_level in the model's raw JSON response is rejected before it
    ever reaches create_roadmap, not just when constructed directly.
    """
    payload = {
        "overview": {
            "headline": "Gap summary",
            "priority_skills": [
                {"skill": "Python", "current_level": 40, "target_level": 150}
            ],
            "estimated_duration": "2 months",
        },
        "steps": [],
    }

    with pytest.raises(ValidationError):
        RoadmapGenerationResult.model_validate_json(json.dumps(payload))


def test_roadmap_generation_result_accepts_in_range_via_json_parse():
    payload = {
        "overview": {
            "headline": "Gap summary",
            "priority_skills": [
                {"skill": "Python", "current_level": 40, "target_level": 80}
            ],
            "estimated_duration": "2 months",
        },
        "steps": [],
    }

    result = RoadmapGenerationResult.model_validate_json(json.dumps(payload))

    assert result.overview.priority_skills[0].target_level == 80
