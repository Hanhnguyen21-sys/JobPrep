-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Ingestion path 1 (Greenhouse/Lever APIs): adds `companies`, `job_postings`,
-- and `job_posting_skill` on top of the existing `skills` table.

create table if not exists public.companies (
    id uuid primary key default gen_random_uuid(),
    name text not null,

    -- 'greenhouse' | 'lever' -- which API shape ats_identifier resolves against.
    ats_platform text,

    -- The board_token (Greenhouse) or site slug (Lever) used to hit that
    -- company's public jobs endpoint, e.g.
    -- https://boards-api.greenhouse.io/v1/boards/{ats_identifier}/jobs
    ats_identifier text,

    career_page_url text,
    created_at timestamptz not null default now(),

    constraint uq_companies_platform_identifier unique (ats_platform, ats_identifier)
);

create table if not exists public.job_postings (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references public.companies (id) on delete cascade,

    external_id text not null,       -- the ATS's own job/posting id

    title text not null,
    location text,
    description text,                -- plain text, HTML stripped on ingest
    url text,

    source_updated_at timestamptz,   -- the ATS's own "updated_at", if it provides one
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    is_active boolean not null default true,

    created_at timestamptz not null default now(),

    constraint uq_job_postings_company_external unique (company_id, external_id)
);

create index if not exists ix_job_postings_company_id on public.job_postings (company_id);
create index if not exists ix_job_postings_is_active on public.job_postings (is_active);

create table if not exists public.job_posting_skill (
    job_posting_id uuid not null references public.job_postings (id) on delete cascade,
    skill_id uuid not null references public.skills (id) on delete cascade,

    requirement_level text not null, -- 'required' | 'preferred'
    evidence text,

    primary key (job_posting_id, skill_id)
);