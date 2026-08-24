-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `job_search_task` -- tracks background refreshes of a normalized
-- job-search query, so POST /jobs/match (see api/routes/jobs.py) can
-- enqueue a refresh and return immediately instead of blocking on the
-- live ATS+OpenAI pipeline. See models/job_search_task.py for the full
-- design note, including the BackgroundTasks durability caveat.

create table if not exists public.job_search_task (
    id uuid primary key default gen_random_uuid(),
    cache_key text not null,
    status text not null default 'queued',  -- queued|running|completed|partial_failure|failed
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    error_summary text
);

create index if not exists ix_job_search_task_cache_key on public.job_search_task (cache_key);

-- Enforces "at most one active (queued/running) refresh per cache key"
-- at the database level -- a partial unique index, not an application-
-- level check, so it holds even if two requests race to enqueue at the
-- same instant. Enqueuing code catches the resulting uniqueness
-- violation and returns the already-active task instead of erroring.
create unique index if not exists uq_job_search_task_active_per_key
    on public.job_search_task (cache_key)
    where status in ('queued', 'running');
