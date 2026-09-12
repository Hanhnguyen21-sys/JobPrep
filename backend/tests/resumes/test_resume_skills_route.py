"""Tests for GET /resumes/skills (api/routes/resumes.py's
get_resume_skills) -- the read-only view of a user's already-linked
resume skills, used by the Dashboard's skills section. `db.execute(...)`
is mocked to return raw row tuples, matching what the route's
`select(...)` actually produces.
"""

import uuid
from unittest.mock import MagicMock

from app.api.routes import resumes
from app.models.user import User


def _fake_user() -> User:
    return User(id=uuid.uuid4(), email="test@example.com", target_position="Software engineer")


def _db_with_rows(rows: list[tuple]) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.all.return_value = rows
    return db


def test_returns_empty_list_when_no_resume_skills_exist():
    db = _db_with_rows([])

    response = resumes.get_resume_skills(current_user=_fake_user(), db=db)

    assert response.skills == []


def test_maps_rows_into_skill_with_context():
    skill_id = uuid.uuid4()
    db = _db_with_rows([(skill_id, "Python", "technical", 75, "high")])

    response = resumes.get_resume_skills(current_user=_fake_user(), db=db)

    assert len(response.skills) == 1
    skill = response.skills[0]
    assert skill.id == skill_id
    assert skill.name == "Python"
    assert skill.category == "technical"
    assert skill.proficiency_level == 75
    assert skill.proficiency_confidence == "high"


def test_defaults_null_proficiency_fields_defensively():
    """Resume-origin rows always have both fields set together in
    practice, but the DB columns are nullable -- a null shouldn't 500.
    """
    skill_id = uuid.uuid4()
    db = _db_with_rows([(skill_id, "Legacy Skill", "technical", None, None)])

    response = resumes.get_resume_skills(current_user=_fake_user(), db=db)

    assert response.skills[0].proficiency_level == 0
    assert response.skills[0].proficiency_confidence == "low"


def test_query_scopes_to_current_user_and_resume_origin():
    user = _fake_user()
    db = _db_with_rows([])

    resumes.get_resume_skills(current_user=user, db=db)

    executed_stmt = db.execute.call_args.args[0]
    compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert f"user_skill.user_id = '{user.id.hex}'" in compiled
    assert "user_skill.origin = 'resume'" in compiled
