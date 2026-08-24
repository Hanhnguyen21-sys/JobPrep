"""Tests for Phase 2 item 6: _bulk_resolve_skills (ingestion/runner.py) --
batched skill lookup/insert replacing one SELECT(+maybe INSERT) per skill
name with at most two round trips for a whole batch.

`db` is a MagicMock throughout -- no real Postgres, same approach as the
rest of this test suite.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.ingestion import runner


def _skill_row(name: str, category: str = "technical"):
    return SimpleNamespace(id=uuid.uuid4(), name=name, category=category)


def test_duplicate_skill_names_resolve_to_one_entry():
    """"Python" / "python" / "PYTHON" across different specs in the same
    batch must resolve to a single Skill, not three separate lookups.
    """
    db = MagicMock()
    db.scalars.return_value = iter([])  # nothing exists yet

    inserted = [_skill_row("Python")]
    db.execute.return_value = inserted

    resolved = runner._bulk_resolve_skills(
        db, [("Python", "technical"), ("python", "technical"), ("PYTHON", "technical")]
    )

    assert len(resolved) == 1
    assert resolved["python"].name == "Python"
    # Only one round trip for the SELECT (existing lookup) and one for
    # the INSERT -- not one pair per skill spec.
    assert db.scalars.call_count == 1
    assert db.execute.call_count == 1


def test_existing_skill_is_found_without_inserting():
    db = MagicMock()
    existing = _skill_row("Python")
    db.scalars.return_value = iter([existing])

    resolved = runner._bulk_resolve_skills(db, [("Python", "technical")])

    assert resolved["python"] is existing
    db.execute.assert_not_called()  # nothing missing -- no INSERT needed


def test_new_skill_not_in_db_gets_bulk_inserted():
    db = MagicMock()
    db.scalars.return_value = iter([])  # not found
    new_row = _skill_row("Rust")
    db.execute.return_value = [new_row]

    resolved = runner._bulk_resolve_skills(db, [("Rust", "technical")])

    # _bulk_resolve_skills wraps the raw RETURNING row into a proper
    # Skill instance (same id/name/category) -- not the same object, but
    # the same identity in DB terms.
    assert resolved["rust"].id == new_row.id
    assert resolved["rust"].name == "Rust"
    db.execute.assert_called_once()


def test_mixed_existing_and_new_skills_in_one_batch():
    db = MagicMock()
    existing = _skill_row("Python")
    db.scalars.return_value = iter([existing])  # "python" already exists
    new_row = _skill_row("Rust")
    db.execute.return_value = [new_row]  # "rust" gets inserted

    resolved = runner._bulk_resolve_skills(
        db, [("Python", "technical"), ("Rust", "technical")]
    )

    assert resolved["python"] is existing
    assert resolved["rust"].id == new_row.id
    db.execute.assert_called_once()  # one bulk INSERT covers just the missing one


def test_uniqueness_race_falls_back_to_reselect():
    """A concurrent request that creates the same skill name between our
    SELECT and INSERT means on_conflict_do_nothing's RETURNING won't
    include a row for it -- _bulk_resolve_skills must re-select whatever
    is still missing rather than leaving it unresolved (which would
    KeyError downstream in _apply_job_skill_extractions_batch).
    """
    db = MagicMock()
    winner_row = _skill_row("Rust")
    db.scalars.side_effect = [
        iter([]),  # first lookup: "rust" doesn't exist yet
        iter([winner_row]),  # re-select after losing the insert race: it does now
    ]
    db.execute.return_value = []  # RETURNING gave back nothing -- lost the race

    resolved = runner._bulk_resolve_skills(db, [("Rust", "technical")])

    assert resolved["rust"] is winner_row
    assert db.scalars.call_count == 2


def test_empty_input_makes_no_db_calls():
    db = MagicMock()
    resolved = runner._bulk_resolve_skills(db, [])
    assert resolved == {}
    db.scalars.assert_not_called()
    db.execute.assert_not_called()
