"""ESCO skill taxonomy, built from a small set of per-domain seed
searches against the ESCO REST API and cached to `esco_taxonomy.json`
(committed to the repo).

This only ever runs at BUILD time:

    python -m app.taxonomy.esco --rebuild

`--rebuild` issues one ESCO `/search?text=<seed>` call per seed phrase in
DOMAIN_SEEDS (no pagination, no full-pillar crawl), folds in the
MANUAL_SKILLS backfill for tools/libraries ESCO doesn't carry, dedupes by
ESCO concept URI, and overwrites the JSON. It needs network and is a
maintenance action -- never something a request or the cron ingestion
triggers. At runtime, `load_or_build_taxonomy()` just reads the committed
JSON (see matcher.py / services/job_skill_extraction.py).

Which seed(s) surfaced each concept is not persisted -- `--rebuild` only
prints it as a per-domain summary so the committed JSON can still be
hand-curated (e.g. spotting an off-topic concept an ESCO free-text search
dragged in) from the rebuild output.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

ESCO_SEARCH_URL = "https://ec.europa.eu/esco/api/search"
_REQUEST_TIMEOUT = 30.0
# Results pulled per seed phrase. ESCO free-text search over a broad
# occupation taxonomy is noisy at the tail, so this stays modest; bump it
# if a rebuild is clearly missing relevant concepts.
_RESULTS_PER_SEED = 30

TAXONOMY_PATH = Path(__file__).with_name("esco_taxonomy.json")

_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_WS = re.compile(r"\s+")
_SLUG = re.compile(r"[^a-z0-9]+")


# --------------------------------------------------------------------------
# Seeds + manual backfill
# --------------------------------------------------------------------------

DOMAIN_SEEDS: dict[str, list[str]] = {
    "software_engineering": [
        "software developer",
        "software engineer",
        "web developer",
        "DevOps engineer",
    ],
    "data_science": [
        "data scientist",
        "data analyst",
        "data engineer",
        "statistician",
    ],
    "ai_ml_engineering": [
        "machine learning",
        "artificial intelligence",
        "natural language processing",
        "computer vision",
    ],
    "quant": [
        "quantitative analyst",
        "financial engineering",
        "algorithmic trading",
        "risk modelling",
        "econometrics",
    ],
}

# ESCO is broad but does not carry every current product / library name
# (PyTorch, FastAPI, Kubernetes, Verilog, SPICE, ...). Add those here,
# each with a display name, alias surface forms, and the domain(s) it
# belongs to. A manual entry whose `name` matches an ESCO concept found
# via the seeds is merged into that concept rather than duplicated.
MANUAL_SKILLS: list[dict[str, Any]] = [
    {
        "name": "Python",
        "aliases": ["Python programming", "programming in Python"],
        "domains": list(DOMAIN_SEEDS),
    },
    {
        "name": "SQL",
        "aliases": ["Structured Query Language"],
        "domains": ["software_engineering", "data_science", "quant"],
    },
    {
        "name": "Machine Learning",
        "aliases": ["machine-learning"],
        "domains": ["data_science", "ai_ml_engineering", "quant"],
    },
    {
        "name": "Natural Language Processing",
        "aliases": ["NLP"],
        "domains": ["data_science", "ai_ml_engineering"],
    },
    {
        "name": "PyTorch",
        "aliases": [],
        "domains": ["ai_ml_engineering", "data_science"],
    },
    {
        "name": "TensorFlow",
        "aliases": [],
        "domains": ["ai_ml_engineering", "data_science"],
    },
    {
        "name": "FastAPI",
        "aliases": [],
        "domains": ["software_engineering"],
    },
    {
        "name": "PostgreSQL",
        "aliases": ["Postgres"],
        "domains": ["software_engineering", "data_science"],
    },
    {
        "name": "Monte Carlo Simulation",
        "aliases": ["Monte Carlo methods", "Monte Carlo modelling"],
        "domains": ["data_science", "ai_ml_engineering", "quant"],
    },
    {
        "name": "Stochastic Calculus",
        "aliases": [],
        "domains": ["quant"],
    },
]


# --------------------------------------------------------------------------
# Output contract
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillEntry:
    """One skill in the cached taxonomy.

    `id` is always present and unique (the ESCO URI, or `manual:<slug>`
    for a MANUAL_SKILLS entry). `uri` is the ESCO concept URI or None.
    `labels` is every lowercased surface form the matcher should look for
    (canonical name + aliases + ESCO alternative labels), de-duplicated.
    `domains` is which DOMAIN_SEEDS bucket(s) surfaced it (kept for
    optional domain-scoped matching later); which specific seed phrases
    hit it is not stored -- see the module docstring.
    """

    id: str
    uri: str | None
    name: str
    labels: tuple[str, ...]
    domains: tuple[str, ...]
    sources: tuple[str, ...]  # ("esco",), ("manual",), or ("esco", "manual")


# --------------------------------------------------------------------------
# Load / persist  (runtime uses only this)
# --------------------------------------------------------------------------


def load_or_build_taxonomy(*, allow_build: bool = False) -> list[SkillEntry]:
    """Return the taxonomy from the committed JSON cache. `allow_build`
    lets the __main__ below fall back to a live rebuild when the cache is
    missing; the extraction path never sets it -- a missing cache there is
    a deployment error, not something to fix with live ESCO calls
    mid-request.
    """
    if TAXONOMY_PATH.exists():
        raw = json.loads(TAXONOMY_PATH.read_text())
        return [
            SkillEntry(
                id=row["id"],
                uri=row.get("uri"),
                name=row["name"],
                labels=tuple(row.get("labels", [])),
                domains=tuple(row.get("domains", [])),
                sources=tuple(row.get("sources", [])),
            )
            for row in raw
        ]

    if not allow_build:
        raise FileNotFoundError(
            f"{TAXONOMY_PATH.name} is missing -- it should be committed to the "
            f"repo. Rebuild it with `python -m app.taxonomy.esco --rebuild`."
        )

    entries, _seeds_by_name = build_taxonomy()
    _write_taxonomy(entries)
    return entries


def _write_taxonomy(entries: list[SkillEntry]) -> None:
    TAXONOMY_PATH.write_text(
        json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2)
    )


# --------------------------------------------------------------------------
# Build (network) -- maintenance only
# --------------------------------------------------------------------------


@dataclass
class _Acc:
    name: str
    labels: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    matched_seeds: set[str] = field(default_factory=set)


def build_taxonomy() -> tuple[list[SkillEntry], dict[str, list[str]]]:
    """One `/search?text=<seed>` call per DOMAIN_SEEDS phrase, deduped by
    ESCO URI, then MANUAL_SKILLS folded in.

    Returns `(entries, seeds_by_name)`. `seeds_by_name` maps each
    ESCO-sourced concept's display name to the sorted seed phrases that
    surfaced it -- build-time provenance only, NOT persisted to the JSON;
    `--rebuild` prints it so the committed file can be hand-curated.
    """
    by_uri: dict[str, _Acc] = {}

    with httpx.Client(
        timeout=_REQUEST_TIMEOUT, headers={"Accept": "application/json"}
    ) as client:
        for domain, seeds in DOMAIN_SEEDS.items():
            for seed in seeds:
                for result in _search(client, seed):
                    uri = result.get("uri")
                    name = _clean(_en(result.get("preferredLabel")) or result.get("title") or "")
                    if not uri or not name:
                        continue
                    acc = by_uri.setdefault(uri, _Acc(name=name))
                    acc.domains.add(domain)
                    acc.matched_seeds.add(seed)
                    acc.labels.update(_label_forms(result))

    entries: list[SkillEntry] = []
    index_by_name: dict[str, int] = {}
    seeds_by_name: dict[str, list[str]] = {}
    for uri, acc in by_uri.items():
        entries.append(
            SkillEntry(
                id=uri,
                uri=uri,
                name=acc.name,
                labels=tuple(_dedupe_lower([acc.name, *acc.labels])),
                domains=tuple(sorted(acc.domains)),
                sources=("esco",),
            )
        )
        index_by_name[acc.name.lower()] = len(entries) - 1
        seeds_by_name[acc.name] = sorted(acc.matched_seeds)

    for manual in MANUAL_SKILLS:
        name = str(manual["name"]).strip()
        aliases = [str(a) for a in manual.get("aliases", [])]
        domains = sorted(str(d) for d in manual.get("domains", []))
        label_forms = _dedupe_lower([name, *aliases])

        idx = index_by_name.get(name.lower())
        if idx is not None:
            existing = entries[idx]
            entries[idx] = replace(
                existing,
                labels=tuple(_dedupe_lower([*existing.labels, *label_forms])),
                domains=tuple(sorted(set(existing.domains) | set(domains))),
                sources=tuple(sorted(set(existing.sources) | {"manual"})),
            )
        else:
            entries.append(
                SkillEntry(
                    id=f"manual:{_slug(name)}",
                    uri=None,
                    name=name,
                    labels=tuple(label_forms),
                    domains=tuple(domains),
                    sources=("manual",),
                )
            )

    entries.sort(key=lambda e: e.name.lower())
    return entries, seeds_by_name


def _search(client: httpx.Client, seed: str) -> list[dict]:
    """A single ESCO search for one seed phrase. No pagination, no retry
    -- this is a build-time script; a transient failure just means
    rerunning `--rebuild`.
    """
    resp = client.get(
        ESCO_SEARCH_URL,
        params={
            "text": seed,
            "type": "skill",
            "language": "en",
            "limit": _RESULTS_PER_SEED,
            "full": "true",
        },
    )
    resp.raise_for_status()
    return (resp.json().get("_embedded") or {}).get("results") or []


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _en(label_map: object) -> str:
    if not isinstance(label_map, dict):
        return ""
    value = label_map.get("en") or label_map.get("en-us") or ""
    return value if isinstance(value, str) else ""


def _en_list(label_map: object) -> list[str]:
    if not isinstance(label_map, dict):
        return []
    value = label_map.get("en") or label_map.get("en-us") or []
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)]


def _label_forms(result: dict) -> list[str]:
    forms = [_clean(_en(result.get("preferredLabel")) or result.get("title") or "")]
    forms += [_clean(a) for a in _en_list(result.get("alternativeLabel"))]
    return [f for f in forms if f]


def _clean(label: str) -> str:
    return _WS.sub(" ", _TRAILING_PAREN.sub("", label)).strip()


def _dedupe_lower(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        norm = value.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _slug(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Search ESCO for every seed and overwrite esco_taxonomy.json (needs network).",
    )
    args = parser.parse_args()

    if args.rebuild:
        print(
            f"Searching ESCO: {sum(len(s) for s in DOMAIN_SEEDS.values())} seed "
            f"phrases across {len(DOMAIN_SEEDS)} domains..."
        )
        built, seeds_by_name = build_taxonomy()
        _write_taxonomy(built)
        manual = sum(1 for e in built if "manual" in e.sources)
        print(
            f"Wrote {TAXONOMY_PATH} -- {len(built)} skills "
            f"({manual} with a manual entry), "
            f"{TAXONOMY_PATH.stat().st_size / 1000:.0f} KB"
        )

        # Per-domain seed provenance (not persisted) -- for hand-curating
        # the JSON: an off-topic concept here is a candidate to prune.
        seed_domain = {s: d for d, ss in DOMAIN_SEEDS.items() for s in ss}
        print("\nESCO concepts matched, by domain:")
        for domain in DOMAIN_SEEDS:
            rows = sorted(
                (name, [s for s in seeds if seed_domain.get(s) == domain])
                for name, seeds in seeds_by_name.items()
                if any(seed_domain.get(s) == domain for s in seeds)
            )
            print(f"\n[{domain}] {len(rows)} concept(s)")
            for name, via in rows:
                print(f"  {name} — matched via: {via}")

        manual_only = sorted(e.name for e in built if e.sources == ("manual",))
        if manual_only:
            print(f"\n[manual backfill] {len(manual_only)} skill(s) not found in ESCO")
            for name in manual_only:
                print(f"  {name}")
    else:
        loaded = load_or_build_taxonomy(allow_build=True)
        print(f"{TAXONOMY_PATH.name}: {len(loaded)} skills")
