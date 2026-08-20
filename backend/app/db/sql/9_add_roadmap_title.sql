-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `title` to roadmaps -- an auto-generated label (built from the
-- selected postings' companies + count + date, see
-- api/routes/roadmaps.py's _build_title) so entries on /roadmaps are easy
-- to tell apart in a history list instead of every card just reading
-- "Roadmap for <target_position>".
--
-- Nullable: existing rows created before this migration have no title --
-- the frontend falls back to "Roadmap for {target_position}" when it's
-- null (see types/roadmap.ts / RoadmapViewer.tsx). New rows always get one
-- set by the application at creation time, not a DB default.

alter table public.roadmaps
    add column if not exists title text;
