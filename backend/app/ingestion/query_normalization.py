
import re

NORMALIZATION_VERSION = "v1"

# Small, explicit, human-reviewed list. Only add an entry here after
# confirming it's an unambiguous abbreviation for the full phrase -- this
# is intentionally not automated/fuzzy.
_ABBREVIATIONS = {
    "swe": "software engineer",
    "data science": "data scientist",
    "quant": "quantitative",
    "quant researcher": "quantitative researcher",
    "quant dev": "quantitative developer",
    "mle": "machine learning engineer",
    "ml engineer": "machine learning engineer",
    "ai/ml engineer": "machine learning engineer",
}


def normalize_query(raw: str) -> str:

    text = raw.strip().lower()
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _ABBREVIATIONS.get(text, text)


def cache_key(raw: str) -> str:

    return f"{NORMALIZATION_VERSION}:{normalize_query(raw)}"


# ---------------------------------------------------------------------------
# Broad title matching -- used to decide whether a job posting's title is
# relevant to a user's target position (ingestion/runner.py,
# api/routes/jobs.py). Deliberately separate from normalize_query/
# cache_key above: those two must stay a single, stable, whole-string
# form forever (job_search_cache's primary key is built from cache_key(),
# and test_cache_key_keeps_distinct_roles_in_separate_buckets pins that
# distinct roles must never collapse into the same bucket) -- this is a
# different, intentionally *broader* comparison used only to decide "is
# this posting relevant", never to key anything.
# ---------------------------------------------------------------------------

# Present in almost every internship posting title regardless of role, so
# they'd otherwise count as "overlap" without indicating an actual match.
_FILLER_TOKENS = {
    "intern", "interns", "internship", "internships",
    "role", "roles", "position", "positions",
    "the", "a", "an", "and", "or", "of", "for", "to", "in",
}

# A token on the left expands to the canonical token(s) on the right, so
# token-set overlap can see through common abbreviations/spelling variants
# a raw substring check can't (e.g. a posting titled "SWE Intern" matching
# a search for "Software Engineer Intern", or "Data Science Intern"
# matching "Data Scientist"). Small and hand-reviewed, same philosophy as
# _ABBREVIATIONS above -- not automated stemming/fuzzy matching.
_TOKEN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "swe": ("software", "engineer"),
    "sde": ("software", "engineer"),
    "ml": ("machine", "learning"),
    "mle": ("machine", "learning", "engineer"),
    "ai": ("artificial", "intelligence"),
    "engineering": ("engineer",),
    "engineers": ("engineer",),
    "scientist": ("science",),
    "scientists": ("science",),
    "quantitative": ("quant",),
    # "Analyst" and "research(er)" roles are used near-interchangeably in
    # early-career quant/finance recruiting (Quantitative Analyst vs.
    # Quantitative Research) -- clustering them lets "Quantitative
    # Analyst" match a posting titled "Quant Research Intern".
    "analyst": ("research",),
    "analysts": ("research",),
    "researcher": ("research",),
    "researchers": ("research",),
}


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _significant_tokens(text: str) -> set[str]:
    """Canonicalized, filler-stripped token set for `text` -- see
    title_matches_query.
    """
    tokens: set[str] = set()
    for token in _tokenize(text):
        if token in _FILLER_TOKENS:
            continue
        tokens.update(_TOKEN_SYNONYMS.get(token, (token,)))
    return tokens


def title_matches_query(query: str, title: str) -> bool:
    """Broader-than-substring relevance check: true when every
    significant (canonicalized, filler-stripped) token in `query` also
    appears -- directly, or via a known synonym/abbreviation -- among
    `title`'s significant tokens.

    Deliberately still simple/explainable on purpose -- a small,
    hand-maintained synonym table and set-overlap, not embeddings or
    semantic search -- but it's broad enough to handle near-miss phrasing
    a raw substring check can't: "Software Engineer Intern" now matches
    postings titled "Software Engineering Internship" or "SWE Intern";
    "Data Scientist" matches "Data Science Intern"; "Machine Learning
    Engineer" matches "AI/ML Engineer Intern"; "Quantitative Analyst"
    matches "Quant Research Intern".
    """
    query_tokens = _significant_tokens(query)
    if not query_tokens:
        return False
    title_tokens = _significant_tokens(title)
    return query_tokens.issubset(title_tokens)
