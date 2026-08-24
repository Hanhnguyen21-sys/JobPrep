"""Tests for Phase 2 item 7: query_normalization.py -- centralized
job-search query normalization used for both the job_search_cache key and
the live title-match needle (ingestion/runner.py)."""

import pytest

from app.ingestion.query_normalization import NORMALIZATION_VERSION, cache_key, normalize_query


@pytest.mark.parametrize(
    "variant",
    ["Software Engineer", "software   engineer", "software-engineer", "SWE", "  Software Engineer  "],
)
def test_variants_share_the_same_normalized_form(variant):
    assert normalize_query(variant) == "software engineer"


@pytest.mark.parametrize(
    "a,b",
    [
        ("Software Engineer", "Software Engineer Intern"),
        ("Software Engineer", "Senior Software Engineer"),
        ("Software Engineer", "Staff Software Engineer"),
        ("Engineer", "Engineering Manager"),
        ("Engineer", "Frontend Engineer"),
        ("Engineer", "Backend Engineer"),
        ("Engineer", "Data Engineer"),
        ("Engineer", "Machine Learning Engineer"),
    ],
)
def test_role_distinguishing_terms_are_never_collapsed(a, b):
    assert normalize_query(a) != normalize_query(b)


def test_cache_key_is_versioned():
    assert cache_key("Software Engineer") == f"{NORMALIZATION_VERSION}:software engineer"


def test_cache_key_shares_one_bucket_across_variants():
    variants = ["Software Engineer", "software   engineer", "software-engineer", "SWE"]
    keys = {cache_key(v) for v in variants}
    assert len(keys) == 1


def test_cache_key_keeps_distinct_roles_in_separate_buckets():
    keys = {cache_key("Software Engineer"), cache_key("Software Engineer Intern")}
    assert len(keys) == 2
