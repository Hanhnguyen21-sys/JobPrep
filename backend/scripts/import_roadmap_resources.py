"""Idempotent catalog sync: imports the top-level roadmap directories
from the developer-roadmap GitHub project's `roadmaps/` folder into
`roadmap_resources` -- one row per roadmap (e.g. slug="python" ->
https://github.com/nilbuild/developer-roadmap/tree/master/roadmaps/python),
NOT one row per article/course link inside it (see migration 18's
docstring for why the earlier per-topic-resource shape was replaced).

Fetches only the immediate `roadmaps/` directory listing via the GitHub
contents API -- never clones the repo, never traverses into any
directory's own `content/` subfolder, never reads/parses a Markdown file.

Never runs automatically (not part of ingestion/runner.py or any cron
yet -- can be added later) and never calls GitHub during roadmap
generation itself; this script is the only thing that talks to GitHub for
this data. services/roadmap_resources.py only ever reads what's already
in the table.

Safety contract this script follows throughout:
  1. Fetch + validate the full directory listing from GitHub FIRST.
  2. Only if that succeeds does it touch the database at all -- applying
     migration 18's (idempotent) DDL if not already applied, then
     upserting by slug and marking any active row whose slug is no
     longer present as inactive.
  3. On any failure in step 1 (network error, unexpected response shape,
     an empty/implausibly small listing), it aborts before touching the
     database -- existing data (rows AND schema) is left exactly as it
     was.

Usage (from backend/, venv active):
    python -m scripts.import_roadmap_resources
    python -m scripts.import_roadmap_resources --repo nilbuild/developer-roadmap --ref master
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.roadmap_resource import RoadmapResource

DEFAULT_REPO = "nilbuild/developer-roadmap"
DEFAULT_REF = "master"

# A directory listing this much smaller than the real repo's ~90
# top-level roadmaps almost certainly means something's wrong upstream
# (a partial/paginated response, a repo restructure, a wrong path) rather
# than a legitimately shrunk catalog -- reject it rather than silently
# deactivating most of the table on bad input.
_MIN_PLAUSIBLE_ENTRIES = 20

_MIGRATION_SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "db" / "sql" / "18_convert_roadmap_resources_to_directory_catalog.sql"
)


class CatalogFetchError(RuntimeError):
    """Raised when the GitHub directory listing can't be fetched or
    doesn't look like a valid, complete roadmaps/ listing. Callers must
    treat this as "make no database changes."
    """


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def fetch_directory_catalog(repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF) -> list[dict]:
    """GET the immediate (non-recursive) listing of `repo`'s `roadmaps/`
    directory and return [{"slug", "title", "url"}, ...] for directory
    entries only -- any file entries are discarded. Never traverses into
    any directory's own contents. Raises CatalogFetchError on any failure
    or implausible result; never returns a partial/best-effort list.
    """
    url = f"https://api.github.com/repos/{repo}/contents/roadmaps"
    try:
        response = httpx.get(
            url,
            params={"ref": ref},
            headers={"Accept": "application/vnd.github+json"},
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0),
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise CatalogFetchError(f"GitHub request failed: {type(exc).__name__}") from exc
    except ValueError as exc:  # response body wasn't valid JSON
        raise CatalogFetchError(f"GitHub response wasn't valid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise CatalogFetchError(
            f"unexpected response shape from GitHub: {type(payload).__name__}"
        )

    entries = [
        {
            "slug": item["name"],
            "title": _title_from_slug(item["name"]),
            "url": item["html_url"],
        }
        for item in payload
        if isinstance(item, dict) and item.get("type") == "dir"
    ]

    if len(entries) < _MIN_PLAUSIBLE_ENTRIES:
        raise CatalogFetchError(
            f"only {len(entries)} directory entries found -- too few to be a "
            f"real roadmaps/ listing (expected at least {_MIN_PLAUSIBLE_ENTRIES})"
        )

    return entries


def _ensure_catalog_schema(db: Session) -> None:
    """Applies migration 18's DDL (idempotent -- see that file's own
    guard) so this script works even against a database where the
    migration hasn't been run manually via the Supabase SQL Editor yet.
    """
    db.execute(text(_MIGRATION_SQL_PATH.read_text()))


def sync_catalog(db: Session, entries: list[dict]) -> dict[str, int]:
    """Upserts `entries` (already fetched + validated by
    fetch_directory_catalog) into roadmap_resources by slug, then marks
    any currently-active row whose slug isn't in `entries` inactive.
    Caller commits. Only meant to be called after a successful fetch --
    never with a partial/failed result.
    """
    _ensure_catalog_schema(db)

    now = datetime.now(timezone.utc)
    values = [
        {
            "slug": entry["slug"],
            "title": entry["title"],
            "url": entry["url"],
            "is_active": True,
            "last_synced_at": now,
        }
        for entry in entries
    ]

    table = RoadmapResource.__table__
    stmt = pg_insert(table).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.slug],
        set_={
            "title": stmt.excluded.title,
            "url": stmt.excluded.url,
            "is_active": True,
            "last_synced_at": stmt.excluded.last_synced_at,
        },
    )
    db.execute(stmt)

    seen_slugs = [entry["slug"] for entry in entries]
    result = db.execute(
        table.update()
        .where(table.c.is_active.is_(True), table.c.slug.notin_(seen_slugs))
        .values(is_active=False)
    )

    return {
        "fetched": len(entries),
        "upserted": len(values),
        "deactivated": result.rowcount or 0,
    }


def import_resources(repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF) -> dict[str, int] | None:
    """Full sync: fetch + validate, then (only on success) sync the
    database. Returns None and leaves the database untouched if the
    fetch fails -- existing data survives any GitHub/network problem.
    """
    try:
        entries = fetch_directory_catalog(repo, ref)
    except CatalogFetchError as exc:
        print(f"[import_roadmap_resources] FAILED -- {exc} -- existing data left unchanged")
        return None

    print(f"[import_roadmap_resources] fetched {len(entries)} roadmap director(y/ies) from {repo}")

    db = SessionLocal()
    try:
        stats = sync_catalog(db, entries)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"[import_roadmap_resources] synced -- "
        f"upserted={stats['upserted']} deactivated={stats['deactivated']}"
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default=DEFAULT_REF)
    args = parser.parse_args()
    import_resources(args.repo, args.ref)
