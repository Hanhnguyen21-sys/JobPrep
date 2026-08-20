-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `overview` to roadmaps -- the structured replacement for the old
-- flat `summary` text column (headline / priority_skills / estimated_duration,
-- see schemas/roadmap.py's RoadmapOverview), part of splitting roadmap
-- output into small, scannable attributes instead of prose paragraphs.
--
-- `summary` is NOT dropped or altered -- it stays in the table, unused by
-- new writes going forward. Rows created before this migration keep their
-- summary text and have `overview = null`; api/routes/roadmaps.py's
-- _to_response backfills a RoadmapOverview from `summary` for those rows
-- at read time, so old roadmaps still render instead of failing to load.
-- Same "leave built-but-unused things in place" pattern already used
-- elsewhere in this project (see setup-progress.md's SkillGapList.tsx
-- note), just applied to a column instead of a component.
--
-- Nullable for the same reason `title` was made nullable in migration 9:
-- existing rows predate this column. New rows always get an overview set
-- by the application at creation time, not a DB default.

alter table public.roadmaps
    add column if not exists overview jsonb;
