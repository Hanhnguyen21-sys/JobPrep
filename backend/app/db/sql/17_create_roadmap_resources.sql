-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Curated learning resources (title/url) mined from the developer-roadmap
-- GitHub project's roadmaps/*/content/*.md files, keyed by that project's
-- own topic slug (e.g. "basic-syntax", "rest-apis") -- see
-- scripts/import_roadmap_resources.py, the only writer of this table.
-- Global reference data, not user-owned -- same "no RLS" shape as
-- companies/job_postings (db/sql/4_create_companies_and_job_postings.sql).

create table if not exists public.roadmap_resources (
    id uuid primary key default gen_random_uuid(),

    -- Bare topic slug from the source repo's filename (the part before
    -- "@<id>"), NOT scoped by which roadmap it came from -- the same
    -- slug legitimately recurs across multiple roadmaps (e.g. "classes"
    -- in both python/ and javascript/), each contributing its own
    -- resources under that shared slug.
    slug text not null,

    title text not null,
    url text not null,

    constraint uq_roadmap_resources_slug_url unique (slug, url)
);

create index if not exists ix_roadmap_resources_slug on public.roadmap_resources (slug);
