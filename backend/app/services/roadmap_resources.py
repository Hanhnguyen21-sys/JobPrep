"""Matches a roadmap step's skill names against the `roadmap_resources`
directory catalog (app/models/roadmap_resource.py) -- the replacement for
services/roadmap.py's LLM-guessed resource links. Pure DB reads: never
calls GitHub, never talks to the OpenAI API. See
scripts/import_roadmap_resources.py for how the catalog itself is kept in
sync (offline, manual/cron -- not from here).

Matching is deliberately simple and explainable, same philosophy as
ingestion/query_normalization.py's abbreviation/synonym tables: normalize
the skill name to a slug shape, check a small hand-curated alias table
for the cases where the repo's own slug doesn't match that normalization
(e.g. "Postgres"/"PostgreSQL" -> the repo's "postgresql-dba"), and
otherwise use the normalized slug directly ("Python" -> "python",
"Machine Learning" -> "machine-learning" already matches the repo's own
slug with no alias needed). A skill with no matching *active* catalog row
produces no resource for it -- never an invented link.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.roadmap_resource import RoadmapResource
from app.schemas.roadmap import Resource

# Small and hand-reviewed, same philosophy as
# ingestion/query_normalization.py's _ABBREVIATIONS/_TOKEN_SYNONYMS --
# only added where the repo's own slug for a well-known skill doesn't
# already match _slugify(skill_name) directly. Keys are matched against
# the lowercased, stripped skill name (before slugifying).
_SKILL_SLUG_ALIASES: dict[str, str] = {
    "ml": "machine-learning",
    "machine learning": "machine-learning",
    "postgres": "postgresql-dba",
    "postgresql": "postgresql-dba",
    "js": "javascript",
    "ts": "typescript",
    "node": "nodejs",
    "node.js": "nodejs",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "k8s": "kubernetes",
    "c++": "cpp",
    "ci/cd": "devops",
}


def _slugify(skill_name: str) -> str:
    """"Machine Learning" -> "machine-learning". Same shape as the
    developer-roadmap repo's own directory names: lowercase, non
    alphanumeric runs collapsed to a single hyphen, no leading/trailing
    hyphen.
    """
    text = skill_name.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _resolve_slug(skill_name: str) -> str | None:
    normalized = skill_name.strip().lower()
    if not normalized:
        return None
    if normalized in _SKILL_SLUG_ALIASES:
        return _SKILL_SLUG_ALIASES[normalized]
    return _slugify(skill_name) or None


def resolve_step_resources(db: Session, skills: list[str]) -> list[Resource]:
    """One `Resource` (type="roadmap") per skill in `skills` that
    resolves to an *active* roadmap_resources row, deduplicated by URL
    within this call (a step's skill list and the alias table can both
    legitimately map two different skill names to the same catalog row).
    Skills with no match are silently omitted -- never an invented link.
    Order-preserving: resources appear in the same order their matching
    skill first appears in `skills`.
    """
    seen_urls: set[str] = set()
    resources: list[Resource] = []

    for skill_name in skills:
        slug = _resolve_slug(skill_name)
        if slug is None:
            continue

        catalog_row = db.scalar(
            select(RoadmapResource).where(
                RoadmapResource.slug == slug,
                RoadmapResource.is_active.is_(True),
            )
        )
        if catalog_row is None or catalog_row.url in seen_urls:
            continue

        seen_urls.add(catalog_row.url)
        resources.append(Resource(title=catalog_row.title, type="roadmap", url=catalog_row.url))

    return resources
