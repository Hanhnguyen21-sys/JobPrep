-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `job_search_cache` -- tracks the last time a full live ATS pull ran
-- for a given (normalized) target position, so
-- ingestion/runner.py's run_targeted_ingestion() can skip straight to
-- querying already-ingested job_postings instead of re-fetching from
-- Greenhouse/Lever and re-running AI extraction on a repeat search within
-- the freshness window. Shared across all users -- a cache hit from one
-- user's search benefits everyone searching the same position, same
-- reasoning as job_postings/job_posting_skill being global, not per-user.

create table if not exists public.job_search_cache (
    target_position text primary key,  -- normalized: trim + lowercase
    last_ingested_at timestamptz not null default now()
);
