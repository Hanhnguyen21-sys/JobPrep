-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `last_interacted_step_order` + `last_interacted_at` to roadmaps --
-- persists which step the user most recently checked/unchecked an action
-- item on, so the Dashboard's "current phase" card can show that step
-- instead of always defaulting to the earliest incomplete one (see
-- repositories/roadmaps.py's set_action_item_done, which writes these, and
-- components/dashboard/ActiveRoadmap.tsx, which reads
-- last_interacted_step_order).
--
-- Nullable, no default: existing rows predate this and have never had an
-- interaction recorded -- null means "fall back to the old first-incomplete-
-- step logic," not "step 0."

alter table public.roadmaps
    add column if not exists last_interacted_step_order integer,
    add column if not exists last_interacted_at timestamptz;
