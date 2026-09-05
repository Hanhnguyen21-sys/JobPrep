"""Roadmap repository -- persistence + lookup for Roadmap +
roadmap_job_posting, shared by api/routes/roadmaps.py.

`get_job_postings_by_ids` used to live here; it moved to
repositories/jobs.py when a since-removed /jobs/skill-gap endpoint needed
the same lookup -- api/routes/roadmaps.py now imports it from there
directly.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.job_posting import JobPosting
from app.models.roadmap import Roadmap


def create_roadmap(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str | None,
    target_position: str,
    summary: str,
    overview: dict,
    steps: list[dict],
    job_postings: list[JobPosting],
) -> Roadmap:
    """Insert a new Roadmap row and its roadmap_job_posting links.
    Flushes (assigns `roadmap.id`) but does not commit -- the caller
    controls the transaction boundary, same convention as
    repositories/skills.py's get_or_create_skill.
    """
    roadmap = Roadmap(
        user_id=user_id,
        title=title,
        target_position=target_position,
        summary=summary,
        overview=overview,
        steps=steps,
    )
    roadmap.source_postings = job_postings
    db.add(roadmap)
    db.flush()
    return roadmap


def get_user_roadmaps(db: Session, user_id: uuid.UUID) -> list[Roadmap]:
    return list(
        db.scalars(
            select(Roadmap)
            .where(Roadmap.user_id == user_id)
            .order_by(Roadmap.created_at.desc())
            .options(
                selectinload(Roadmap.source_postings).selectinload(
                    JobPosting.company
                )
            )
        )
    )


def get_roadmap(
    db: Session, user_id: uuid.UUID, roadmap_id: uuid.UUID
) -> Roadmap | None:
    return db.scalar(
        select(Roadmap)
        .where(Roadmap.id == roadmap_id, Roadmap.user_id == user_id)
        .options(
            selectinload(Roadmap.source_postings).selectinload(JobPosting.company)
        )
    )


def set_action_item_done(
    db: Session,
    roadmap: Roadmap,
    *,
    step_order: int,
    item_index: int,
    done: bool,
    interacted_at: datetime,
) -> dict[str, list[int]]:
    """Marks (or unmarks) one action item done for one step, persisting
    into Roadmap.completed_action_items. Reassigns the whole dict rather
    than mutating the existing one in place -- SQLAlchemy's dirty-tracking
    doesn't see an in-place mutation of a JSONB column's Python dict,
    only a reassignment of the attribute. Flushes but does not commit --
    caller's transaction, same convention as create_roadmap.

    Also records this as the roadmap's most recent interaction
    (last_interacted_step_order/last_interacted_at) -- regardless of
    `done`, since unchecking an item is still an interaction with that
    step, same as checking one. Guarded by `interacted_at` so a
    slow/delayed request for an *older* interaction can't roll this
    pointer back past a newer interaction that already landed; the
    item's own checked state above is unaffected by this guard either
    way.
    """
    current = {
        key: list(indices) for key, indices in (roadmap.completed_action_items or {}).items()
    }
    key = str(step_order)
    indices = set(current.get(key, []))

    if done:
        indices.add(item_index)
    else:
        indices.discard(item_index)

    if indices:
        current[key] = sorted(indices)
    else:
        current.pop(key, None)

    roadmap.completed_action_items = current

    if roadmap.last_interacted_at is None or interacted_at >= roadmap.last_interacted_at:
        roadmap.last_interacted_step_order = step_order
        roadmap.last_interacted_at = interacted_at

    db.flush()
    return current


def delete_roadmap(db: Session, user_id: uuid.UUID, roadmap_id: uuid.UUID) -> bool:
    """Delete a roadmap if it exists and belongs to user_id. Returns True if
    a row was deleted, False if no matching roadmap was found (caller 404s
    in that case rather than silently no-opping). roadmap_job_posting links
    cascade-delete at the DB level (`on delete cascade`, in
    db/sql/8_create_roadmaps.sql) -- nothing to clean up here beyond the
    roadmap row itself. Flushes but does not commit -- caller's transaction,
    same convention as create_roadmap.
    """
    roadmap = get_roadmap(db, user_id, roadmap_id)
    if roadmap is None:
        return False
    db.delete(roadmap)
    db.flush()
    return True
