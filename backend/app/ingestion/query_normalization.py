
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
    
    text = raw.strip().lower()
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _ABBREVIATIONS.get(text, text)


def cache_key(raw: str) -> str:
    
    return f"{NORMALIZATION_VERSION}:{normalize_query(raw)}"
