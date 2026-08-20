-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `roadmaps` + `roadmap_job_posting` -- the User_Job_Selection ->
-- roadmap-generation step. A roadmap is generated once from a snapshot of
-- up to 10 selected job postings' descriptions combined into a single AI
-- call (see services/roadmap.py, api/routes/roadmaps.py);
-- `roadmap_job_posting` records which postings a given roadmap was built
-- from, same many-to-many convention as job_posting_skill / user_skill.
--
-- No separate `user_job_selection` table -- the frontend keeps the
-- checkbox selection in memory only (see Step 5b) and sends the chosen
-- job_posting_ids directly in the POST /roadmaps body each time, so
-- there's nothing selection-shaped to persist independently of the
-- roadmap it produced.

create table if not exists public.roadmaps (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,

    -- Snapshot of the user's target_position at generation time --
    -- users.target_position can change later; this is what the roadmap
    -- was actually generated for.
    target_position text not null,
    summary text not null,

    -- list of {order, title, description, skills_to_develop} -- see
    -- models/roadmap.py's docstring for why this is one JSONB blob
    -- rather than a normalized roadmap_step table.
    steps jsonb not null,

    created_at timestamptz not null default now()
);

create index if not exists ix_roadmaps_user_id on public.roadmaps (user_id);

create table if not exists public.roadmap_job_posting (
    roadmap_id uuid not null references public.roadmaps (id) on delete cascade,
    job_posting_id uuid not null references public.job_postings (id) on delete cascade,

    primary key (roadmap_id, job_posting_id)
);
