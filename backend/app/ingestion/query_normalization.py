"""Centralized normalization for free-text job-search queries -- used as
both the job_search_cache key and the live-pipeline title-match needle
(ingestion/runner.py), so "Software Engineer" / "software   engineer" /
"software-engineer" / "SWE" all share one cache bucket and match the same
postings, instead of each being treated as a completely distinct search
the way plain strip().lower() did before.

Deliberately NOT a stemmer or keyword-remover -- nothing here ever
deletes a word. That's what keeps role-distinguishing terms from being
silently collapsed together: "software engineer" and "software engineer
intern" always normalize to two different strings, and likewise for
senior/staff/manager/frontend/backend/data/machine learning -- none of
those words are touched.
"""

import re

# Bump this if normalize_query()'s behavior ever changes in a way that
# could make an old cache row look like a hit/miss for a query it wasn't
# actually computed for -- see cache_key()'s docstring.
NORMALIZATION_VERSION = "v1"

# Small, explicit, human-reviewed list. Only add an entry here after
# confirming it's an unambiguous abbreviation for the full phrase -- this
# is intentionally not automated/fuzzy.
_ABBREVIATIONS = {
    "swe": "software engineer",
}


def normalize_query(raw: str) -> str:
    """Canonical form of a job-search query string. Collapses
    leading/trailing and repeated internal whitespace, casing, and
    hyphen/underscore-vs-space variants; expands a small explicit set of
    approved abbreviations. Preserves the original meaning otherwise --
    callers that need to show the user's original input back to them
    (logging, UI) should keep the raw string separately, not this.
    """
    text = raw.strip().lower()
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _ABBREVIATIONS.get(text, text)


def cache_key(raw: str) -> str:
    """job_search_cache.target_position value. Versioned (see
    NORMALIZATION_VERSION) so a future change to normalize_query() can't
    make an old row silently look like a hit (or a miss) for a query it
    was never actually computed for -- old rows just stay permanently
    stale/unreachable under a version bump, which is harmless (they don't
    cause an incorrect hit; they just eventually get cleaned up or ignored).
    """
    return f"{NORMALIZATION_VERSION}:{normalize_query(raw)}"
