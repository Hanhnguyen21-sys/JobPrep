"""Tests for the Dashboard "current phase" fix: Roadmap.last_interacted_*
(models/roadmap.py) is set whenever repositories/roadmaps.py's
set_action_item_done runs, and is exposed via
api/routes/roadmaps.py's _to_response.

No live Postgres is used -- `Roadmap` rows are plain in-memory ORM
instances (never flushed/queried) and `db` is a MagicMock, since
set_action_item_done only calls db.flush(). Same approach as
tests/ingestion/test_company_sources.py.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.api.routes.roadmaps import _to_response
from app.models.roadmap import Roadmap
from app.repositories.roadmaps import set_action_item_done

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_roadmap(**overrides) -> Roadmap:
    roadmap = Roadmap(
        id=uuid.uuid4(),
        user_id="00000000-0000-0000-0000-000000000001",
        created_at=NOW,
        title="Test roadmap",
        target_position="Software Engineer",
        summary="Summary",
        overview={"headline": "h", "priority_skills": [], "estimated_duration": ""},
        steps=[
            {
                "order": 1,
                "title": "Phase 1",
                "focus_skill": "",
                "skills": [],
                "why_it_matters": "",
                "action_items": ["a", "b"],
                "resources": [],
                "project": None,
                "duration": "",
                "success_criteria": [],
            },
            {
                "order": 2,
                "title": "Phase 2",
                "focus_skill": "",
                "skills": [],
                "why_it_matters": "",
                "action_items": ["c", "d"],
                "resources": [],
                "project": None,
                "duration": "",
                "success_criteria": [],
            },
        ],
        **overrides,
    )
    roadmap.source_postings = []
    return roadmap


def test_first_interaction_sets_pointer():
    roadmap = _make_roadmap()
    db = MagicMock()

    set_action_item_done(db, roadmap, step_order=1, item_index=0, done=True, interacted_at=NOW)

    assert roadmap.last_interacted_step_order == 1
    assert roadmap.last_interacted_at == NOW


def test_interacting_with_later_step_updates_pointer_even_if_earlier_step_incomplete():
    roadmap = _make_roadmap()
    db = MagicMock()

    # Phase 1 has an unchecked item ("b"), never touched.
    set_action_item_done(db, roadmap, step_order=1, item_index=0, done=True, interacted_at=NOW)
    set_action_item_done(
        db,
        roadmap,
        step_order=2,
        item_index=0,
        done=True,
        interacted_at=NOW + timedelta(seconds=1),
    )

    assert roadmap.last_interacted_step_order == 2
    # Phase 1's item 1 ("b") is still unchecked -- confirms the pointer
    # moved to Phase 2 despite Phase 1 being incomplete.
    assert roadmap.completed_action_items == {"1": [0], "2": [0]}


def test_unchecking_an_item_still_updates_the_pointer():
    roadmap = _make_roadmap(
        completed_action_items={"1": [0]},
        last_interacted_step_order=1,
        last_interacted_at=NOW,
    )
    db = MagicMock()

    set_action_item_done(
        db,
        roadmap,
        step_order=1,
        item_index=0,
        done=False,
        interacted_at=NOW + timedelta(seconds=1),
    )

    assert roadmap.completed_action_items == {}
    assert roadmap.last_interacted_step_order == 1
    assert roadmap.last_interacted_at == NOW + timedelta(seconds=1)


def test_older_interaction_does_not_regress_the_pointer():
    roadmap = _make_roadmap(last_interacted_step_order=2, last_interacted_at=NOW)
    db = MagicMock()

    # A delayed request for an interaction that actually happened *before*
    # the one already recorded -- e.g. it was in flight and resolved late.
    set_action_item_done(
        db,
        roadmap,
        step_order=1,
        item_index=0,
        done=True,
        interacted_at=NOW - timedelta(seconds=5),
    )

    # The pointer isn't rolled back...
    assert roadmap.last_interacted_step_order == 2
    assert roadmap.last_interacted_at == NOW
    # ...but the item itself is still correctly checked off.
    assert roadmap.completed_action_items == {"1": [0]}


def test_response_exposes_last_interacted_step_order():
    roadmap = _make_roadmap(last_interacted_step_order=2, last_interacted_at=NOW)

    response = _to_response(roadmap)

    assert response.last_interacted_step_order == 2


def test_response_defaults_to_none_when_never_interacted():
    roadmap = _make_roadmap()

    response = _to_response(roadmap)

    assert response.last_interacted_step_order is None


def test_pointers_are_independent_per_roadmap():
    roadmap_a = _make_roadmap()
    roadmap_b = _make_roadmap()
    db = MagicMock()

    set_action_item_done(db, roadmap_a, step_order=2, item_index=0, done=True, interacted_at=NOW)

    assert roadmap_a.last_interacted_step_order == 2
    assert roadmap_b.last_interacted_step_order is None
