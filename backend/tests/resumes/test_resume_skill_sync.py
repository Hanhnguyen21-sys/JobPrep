"""Integration tests for _sync_resume_skills' actual persistence
behavior -- upsert, stale-row deletion scoped to origin="resume", and
duplicate-name dedup all live inside a single SQL statement/query each
(pg_insert ... on_conflict_do_update, a scoped DELETE, a case-insensitive
SELECT), which a MagicMock db can't meaningfully exercise. These run
against a throwaway, local-only Postgres database created and dropped by
this module -- never against the project's real Supabase database (see
app/db/session.py / .env), which this module does not import or touch.

Skipped automatically when no local Postgres server is reachable (e.g. in
an environment without one installed).
"""

import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.resumes import _sync_resume_skills
from app.models.skill import Skill
from app.models.user import User, user_skill
from app.services.skill_extraction import ExtractedSkill, SkillExtractionResult

DB_NAME = "jobprep_resume_sync_test"
DB_URL = f"postgresql:///{DB_NAME}"


def _local_postgres_available() -> bool:
    try:
        return subprocess.run(["pg_isready"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not _local_postgres_available(),
    reason="requires a local Postgres server (pg_isready) to run persistence tests",
)


@pytest.fixture()
def session():
    subprocess.run(["dropdb", "--if-exists", DB_NAME], capture_output=True)
    subprocess.run(["createdb", DB_NAME], check=True, capture_output=True)

    engine = create_engine(DB_URL)
    try:
        User.metadata.create_all(engine, tables=[User.__table__, Skill.__table__, user_skill])
        db = Session(bind=engine)
        try:
            yield db
        finally:
            db.close()
    finally:
        engine.dispose()
        subprocess.run(["dropdb", "--if-exists", DB_NAME], capture_output=True)


def _make_user(db: Session) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com")
    db.add(user)
    db.commit()
    return user


def _extraction(*, technical: list[ExtractedSkill] | None = None, soft: list[ExtractedSkill] | None = None):
    return SkillExtractionResult(technical_skills=technical or [], soft_skills=soft or [])


def _user_skill_rows(db: Session, user_id) -> list:
    return list(
        db.execute(select(user_skill).where(user_skill.c.user_id == user_id)).all()
    )


# ---------------------------------------------------------------------------
# Proficiency persistence
# ---------------------------------------------------------------------------


def test_extracted_proficiency_is_persisted(session):
    user = _make_user(session)
    result = _extraction(
        technical=[ExtractedSkill(name="Python", proficiency_level=72, proficiency_confidence="high")]
    )

    response = _sync_resume_skills(session, user, result)

    assert response.skills[0].proficiency_level == 72
    assert response.skills[0].proficiency_confidence == "high"

    rows = _user_skill_rows(session, user.id)
    assert len(rows) == 1
    assert rows[0].proficiency_level == 72
    assert rows[0].proficiency_confidence == "high"
    assert rows[0].origin == "resume"


# ---------------------------------------------------------------------------
# Resubmission: update existing, insert new, delete stale
# ---------------------------------------------------------------------------


def test_resubmission_updates_proficiency_for_existing_skill(session):
    user = _make_user(session)
    _sync_resume_skills(
        session,
        user,
        _extraction(technical=[ExtractedSkill(name="Python", proficiency_level=30, proficiency_confidence="low")]),
    )

    _sync_resume_skills(
        session,
        user,
        _extraction(technical=[ExtractedSkill(name="Python", proficiency_level=85, proficiency_confidence="high")]),
    )

    rows = _user_skill_rows(session, user.id)
    assert len(rows) == 1
    assert rows[0].proficiency_level == 85
    assert rows[0].proficiency_confidence == "high"


def test_resubmission_inserts_newly_detected_skills(session):
    user = _make_user(session)
    _sync_resume_skills(
        session, user, _extraction(technical=[ExtractedSkill(name="Python", proficiency_level=50, proficiency_confidence="medium")])
    )

    _sync_resume_skills(
        session,
        user,
        _extraction(
            technical=[
                ExtractedSkill(name="Python", proficiency_level=50, proficiency_confidence="medium"),
                ExtractedSkill(name="Docker", proficiency_level=20, proficiency_confidence="low"),
            ]
        ),
    )

    rows = _user_skill_rows(session, user.id)
    names = {session.get(Skill, row.skill_id).name for row in rows}
    assert names == {"Python", "Docker"}


def test_resubmission_deletes_stale_resume_origin_skills(session):
    user = _make_user(session)
    _sync_resume_skills(
        session,
        user,
        _extraction(
            technical=[
                ExtractedSkill(name="Python", proficiency_level=50, proficiency_confidence="medium"),
                ExtractedSkill(name="Docker", proficiency_level=20, proficiency_confidence="low"),
            ]
        ),
    )

    # Second resume no longer mentions Docker.
    _sync_resume_skills(
        session,
        user,
        _extraction(technical=[ExtractedSkill(name="Python", proficiency_level=55, proficiency_confidence="medium")]),
    )

    rows = _user_skill_rows(session, user.id)
    names = {session.get(Skill, row.skill_id).name for row in rows}
    assert names == {"Python"}


def test_manually_added_or_other_origin_skills_are_preserved(session):
    user = _make_user(session)
    skill = Skill(name="Leadership", category="soft")
    session.add(skill)
    session.flush()
    session.execute(
        user_skill.insert().values(
            user_id=user.id, skill_id=skill.id, origin="manual"
        )
    )
    session.commit()

    _sync_resume_skills(
        session,
        user,
        _extraction(technical=[ExtractedSkill(name="Python", proficiency_level=50, proficiency_confidence="medium")]),
    )

    rows = _user_skill_rows(session, user.id)
    by_origin = {row.origin: session.get(Skill, row.skill_id).name for row in rows}
    assert by_origin == {"manual": "Leadership", "resume": "Python"}


# ---------------------------------------------------------------------------
# Duplicate normalized names
# ---------------------------------------------------------------------------


def test_duplicate_normalized_names_do_not_create_duplicate_rows(session):
    user = _make_user(session)
    result = _extraction(
        technical=[
            ExtractedSkill(name="Python", proficiency_level=40, proficiency_confidence="low"),
            ExtractedSkill(name="python", proficiency_level=90, proficiency_confidence="high"),
            ExtractedSkill(name="  PYTHON  ", proficiency_level=10, proficiency_confidence="low"),
        ]
    )

    response = _sync_resume_skills(session, user, result)

    assert len(response.skills) == 1
    rows = _user_skill_rows(session, user.id)
    assert len(rows) == 1
    # First occurrence wins -- same dedup rule _sync_resume_skills already
    # applies (dict.setdefault keyed by normalized name).
    assert rows[0].proficiency_level == 40
