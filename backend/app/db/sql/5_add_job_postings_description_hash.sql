-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `description_hash` to job_postings -- added to ingestion/runner.py
-- (sha256 of `description`, used to skip re-running AI skill extraction on
-- postings whose content hasn't changed since the last ingestion run)
-- after 4_create_companies_and_job_postings.sql had already been executed,
-- so it needs its own ALTER TABLE rather than folding into that file.

alter table public.job_postings
    add column if not exists description_hash text;
