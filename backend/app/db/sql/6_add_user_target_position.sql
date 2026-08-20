-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `target_position` to users -- the job title/role a user is looking
-- for, captured alongside their resume submission. Persisted (unlike
-- resume text itself, which is discarded after extraction) because it's
-- a stable profile attribute reused by api/routes/jobs.py's targeted
-- ingestion endpoint on every "Find Matching Jobs" call, not just the one
-- that first set it.

alter table public.users
    add column if not exists target_position text;
