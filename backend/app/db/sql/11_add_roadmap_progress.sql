-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `completed_action_items` to roadmaps -- persists which of each
-- step's action_items the user has checked off, so the checklist survives
-- reload and reads the same on /roadmaps and the Dashboard's roadmap
-- summary instead of resetting on every mount (PhaseChecklist.tsx used to
-- be local useState only -- see repositories/roadmaps.py's
-- set_action_item_done for the write path this backs).
--
-- Shape: {"<step_order>": [<action_item index>, ...]}, e.g. {"1": [0, 2]}
-- means step order 1 has action_items[0] and action_items[2] checked off.
-- A step with nothing checked simply has no key, rather than an empty
-- array, to keep the JSON small.
--
-- Nullable, no default: existing rows predate this column and have nothing
-- completed yet. api/routes/roadmaps.py's _to_response treats null the
-- same as {} at read time.

alter table public.roadmaps
    add column if not exists completed_action_items jsonb;
