-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Converts `roadmap_resources` from migration 17's per-markdown-topic
-- resource-link shape (~23k article/video/course rows, one per link
-- inside roadmaps/*/content/*.md) into a per-roadmap directory catalog:
-- one row per top-level roadmaps/<slug> directory in the
-- developer-roadmap GitHub repo. See scripts/import_roadmap_resources.py
-- (rewritten to use the GitHub contents API against `roadmaps/` only --
-- no repo clone, no content/*.md parsing) for the importer that
-- populates this new shape, and app/services/roadmap_resources.py for
-- how roadmap generation matches a skill name against it.
--
-- The old per-topic-resource rows are preserved, not dropped --
-- renamed to `roadmap_resources_topic_backup` so they remain queryable
-- if ever needed, since they took a real (slow) full-repo clone to
-- build. Idempotent: safe to run more than once -- the rename only
-- fires if `roadmap_resources` still has the old (pre-catalog) shape.

do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'roadmap_resources'
          and column_name = 'is_active'
    ) then
        return; -- already migrated to the catalog shape
    end if;

    if exists (
        select 1 from information_schema.tables
        where table_schema = 'public' and table_name = 'roadmap_resources'
    ) then
        alter table public.roadmap_resources
            rename to roadmap_resources_topic_backup;
    end if;
end $$;

create table if not exists public.roadmap_resources (
    id uuid primary key default gen_random_uuid(),

    -- Top-level roadmaps/<slug> directory name (e.g. "machine-learning",
    -- "python") -- one row per roadmap.
    slug text not null unique,

    title text not null,   -- display name, derived from slug
    url text not null,     -- GitHub directory URL (contents API's html_url)

    is_active boolean not null default true,
    last_synced_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists ix_roadmap_resources_is_active on public.roadmap_resources (is_active);
