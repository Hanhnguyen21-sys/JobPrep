"""Tests for repositories/jobs.py::aggregate_required_skills -- focused on
`postings_requiring_count`, the field added so services/roadmap.py's
skill-gap prompt has real data behind the "required by more of the given
postings" instruction it already gave the model (previously that
instruction had nothing to point at -- see the roadmap skill-gap audit).

MagicMock `db` throughout, no real Postgres -- same convention as the rest
of this suite. `db.execute` is given a `side_effect` (rather than a flat
`return_value`) where a test needs to inspect the actual SQL statement
`aggregate_required_skills` built, not just control what rows come back.
"""

import uuid
from unittest.mock import MagicMock

from app.repositories import jobs as repo


def _fake_posting(posting_id: uuid.UUID) -> MagicMock:
    return MagicMock(id=posting_id)


def _mock_db_returning(rows: list[tuple]) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.all.return_value = rows
    return db


def test_no_postings_short_circuits_without_querying():
    db = MagicMock()

    result = repo.aggregate_required_skills(db, [])

    assert result == []
    db.execute.assert_not_called()


def test_skill_required_by_a_single_posting_has_count_one():
    skill_id = uuid.uuid4()
    posting_id = uuid.uuid4()
    db = _mock_db_returning(
        [(skill_id, "Python", "technical", "required", posting_id)]
    )

    result = repo.aggregate_required_skills(db, [_fake_posting(posting_id)])

    assert len(result) == 1
    assert result[0]["skill_id"] == skill_id
    assert result[0]["postings_requiring_count"] == 1


def test_skill_required_by_multiple_postings_counts_each_distinct_posting():
    skill_id = uuid.uuid4()
    p1, p2, p3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _mock_db_returning(
        [
            (skill_id, "Python", "technical", "preferred", p1),
            (skill_id, "Python", "technical", "required", p2),  # required wins
            (skill_id, "Python", "technical", "preferred", p3),
        ]
    )

    result = repo.aggregate_required_skills(
        db, [_fake_posting(p) for p in (p1, p2, p3)]
    )

    assert len(result) == 1
    assert result[0]["postings_requiring_count"] == 3
    assert result[0]["requirement_level"] == "required"


def test_count_is_scoped_to_the_given_postings_not_every_posting_in_the_db():
    """The count must come from the postings the caller actually passed in
    -- not from every posting in the database that happens to need this
    skill. Verified two ways: (1) the rows a real WHERE ... IN (in_scope)
    query would return never include the out-of-scope posting, so the
    count is right; (2) the compiled statement's bound parameters are
    inspected directly to confirm the WHERE clause itself was built from
    `job_postings`' ids -- controlling the mocked rows alone would pass
    even with a broken/missing WHERE clause, so that part alone isn't
    sufficient proof of scoping.
    """
    skill_id = uuid.uuid4()
    in_scope = [uuid.uuid4(), uuid.uuid4()]
    out_of_scope = uuid.uuid4()  # some other posting needing this skill, not selected

    captured = {}

    def fake_execute(stmt):
        captured["stmt"] = stmt
        result = MagicMock()
        # A real WHERE job_posting_id IN (in_scope) would never surface
        # out_of_scope's row, regardless of what's in the real DB.
        result.all.return_value = [
            (skill_id, "Python", "technical", "required", pid) for pid in in_scope
        ]
        return result

    db = MagicMock()
    db.execute.side_effect = fake_execute

    result = repo.aggregate_required_skills(db, [_fake_posting(p) for p in in_scope])

    assert result[0]["postings_requiring_count"] == 2

    bound_ids: set = set()
    for value in captured["stmt"].compile().params.values():
        bound_ids.update(value) if isinstance(value, list) else bound_ids.add(value)

    assert set(in_scope) <= bound_ids
    assert out_of_scope not in bound_ids


def test_postings_requiring_count_is_additive_existing_fields_unchanged():
    """/jobs/match's _to_skill_gap_items only reads skill_id/name/category/
    requirement_level -- confirm those are untouched and the new field is
    purely additive, not a replacement.
    """
    skill_id = uuid.uuid4()
    posting_id = uuid.uuid4()
    db = _mock_db_returning(
        [(skill_id, "SQL", "technical", "preferred", posting_id)]
    )

    result = repo.aggregate_required_skills(db, [_fake_posting(posting_id)])

    assert result == [
        {
            "skill_id": skill_id,
            "name": "SQL",
            "category": "technical",
            "requirement_level": "preferred",
            "postings_requiring_count": 1,
        }
    ]
