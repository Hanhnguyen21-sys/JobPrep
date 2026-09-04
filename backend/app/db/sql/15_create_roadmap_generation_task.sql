-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `roadmap_generation_task` -- tracks background POST /roadmaps
-- generations, so that route can return immediately instead of blocking
-- on up to MAX_SELECTED_POSTINGS sequential description fetches plus two
-- LLM calls. See models/roadmap_generation_task.py for the full design
-- note, including the BackgroundTasks durability caveat.
--
-- Unlike job_search_task, no partial-unique-index dedup here -- a roadmap
-- generation is per-user/per-selection, not a shared cache key, so
-- there's nothing to dedupe concurrent requests against.

create table if not exists public.roadmap_generation_task (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,
    job_posting_ids uuid[] not null,
    status text not null default 'queued',  -- queued|running|completed|failed
    roadmap_id uuid references public.roadmaps (id) on delete set null,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    error_summary text
);

create index if not exists ix_roadmap_generation_task_user_id
    on public.roadmap_generation_task (user_id);
