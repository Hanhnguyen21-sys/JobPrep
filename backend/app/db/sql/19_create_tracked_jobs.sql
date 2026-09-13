-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `tracked_jobs` -- persistence for the Tracker page
-- (api/routes/tracker.py). A row is created automatically (status
-- defaults to 'saved') the first time a user selects a posting on Job
-- Match; unselecting it there never deletes this row -- only Tracker's
-- own Remove action does, and that only removes this user's row, never
-- the shared job_postings row it points at.
--
-- No backfill needed for existing installs: the frontend's Job Match
-- selection has only ever been in-memory (see roadmaps' migration note
-- in 8_create_roadmaps.sql), so there is no prior persisted selection
-- state to seed tracked_jobs from.

create table if not exists public.tracked_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,
    job_posting_id uuid not null references public.job_postings (id) on delete cascade,

    -- 'saved' | 'applied' | 'interview' | 'offer' | 'rejected' | 'withdrawn'
    status text not null default 'saved'
        constraint ck_tracked_jobs_status_values
        check (status in ('saved', 'applied', 'interview', 'offer', 'rejected', 'withdrawn')),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    -- One tracked row per user/posting pair -- re-selecting an
    -- already-tracked posting on Job Match must not create a duplicate;
    -- repositories/tracked_jobs.py's get_or_create_tracked_job relies on
    -- this at the database level to stay race-safe, same pattern as
    -- job_search_task's uq_job_search_task_active_per_key.
    constraint uq_tracked_jobs_user_job unique (user_id, job_posting_id)
);

create index if not exists ix_tracked_jobs_user_id on public.tracked_jobs (user_id);
create index if not exists ix_tracked_jobs_job_posting_id on public.tracked_jobs (job_posting_id);
