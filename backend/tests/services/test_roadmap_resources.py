"""Tests for services/roadmap_resources.py -- matching a roadmap step's
skills against the roadmap_resources directory catalog. `db.scalar` is
faked via a small helper that inspects the compiled WHERE clause (literal
binds) rather than a real database, same "no real DB in tests" convention
as the rest of this suite.
"""

import re
from unittest.mock import MagicMock

from app.services.roadmap_resources import _resolve_slug, resolve_step_resources


class _FakeRow:
    def __init__(self, slug: str, title: str, url: str, is_active: bool = True):
        self.slug = slug
        self.title = title
        self.url = url
        self.is_active = is_active


def _fake_db(rows: list[_FakeRow]) -> MagicMock:
    """A MagicMock db whose .scalar(stmt) resolves the slug the query
    filtered on (via compiling with literal binds) and returns the
    matching row only if it's marked active in `rows` -- mirroring
    "WHERE slug = :slug AND is_active IS true" without a real database.
    """
    by_slug = {row.slug: row for row in rows}
    db = MagicMock()

    def _scalar(stmt):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        match = re.search(r"roadmap_resources\.slug = '([^']+)'", compiled)
        if not match:
            return None
        row = by_slug.get(match.group(1))
        return row if row is not None and row.is_active else None

    db.scalar.side_effect = _scalar
    return db


# ---------------------------------------------------------------------------
# _resolve_slug -- alias table + slugify fallback
# ---------------------------------------------------------------------------


def test_resolve_slug_direct_match_needs_no_alias():
    assert _resolve_slug("Python") == "python"
    assert _resolve_slug("Machine Learning") == "machine-learning"


def test_resolve_slug_aliases_ml_and_machine_learning():
    assert _resolve_slug("ML") == "machine-learning"
    assert _resolve_slug("Machine Learning") == "machine-learning"


def test_resolve_slug_aliases_postgres_and_postgresql():
    assert _resolve_slug("Postgres") == "postgresql-dba"
    assert _resolve_slug("PostgreSQL") == "postgresql-dba"


def test_resolve_slug_returns_none_for_blank():
    assert _resolve_slug("") is None
    assert _resolve_slug("   ") is None


# ---------------------------------------------------------------------------
# resolve_step_resources -- catalog matching, active-only, dedup
# ---------------------------------------------------------------------------


def test_alias_resolves_to_stored_catalog_url():
    db = _fake_db(
        [_FakeRow("machine-learning", "Machine Learning", "https://github.com/.../machine-learning")]
    )

    resources = resolve_step_resources(db, ["ML"])

    assert len(resources) == 1
    assert resources[0].type == "roadmap"
    assert resources[0].title == "Machine Learning"
    assert resources[0].url == "https://github.com/.../machine-learning"


def test_unknown_skill_produces_no_resource():
    db = _fake_db([_FakeRow("python", "Python", "https://github.com/.../python")])

    resources = resolve_step_resources(db, ["Some Totally Unheard Of Skill"])

    assert resources == []


def test_inactive_catalog_row_is_not_matched():
    db = _fake_db(
        [_FakeRow("cobol", "Cobol", "https://github.com/.../cobol", is_active=False)]
    )

    resources = resolve_step_resources(db, ["Cobol"])

    assert resources == []


def test_dedup_within_step_when_two_skills_map_to_same_row():
    db = _fake_db(
        [_FakeRow("postgresql-dba", "Postgresql Dba", "https://github.com/.../postgresql-dba")]
    )

    resources = resolve_step_resources(db, ["Postgres", "PostgreSQL"])

    assert len(resources) == 1


def test_multiple_distinct_matches_are_all_returned():
    db = _fake_db(
        [
            _FakeRow("python", "Python", "https://github.com/.../python"),
            _FakeRow("docker", "Docker", "https://github.com/.../docker"),
        ]
    )

    resources = resolve_step_resources(db, ["Python", "Docker", "Unmatched Skill"])

    urls = {r.url for r in resources}
    assert urls == {"https://github.com/.../python", "https://github.com/.../docker"}
