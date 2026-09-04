-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `proficiency_level`/`proficiency_confidence` to user_skill so resume
-- skill extraction can store an estimated proficiency (0-100, plus how
-- reliable that estimate is) instead of per-skill *extraction* confidence.
-- See models/user.py for the SQLAlchemy side and
-- services/skill_extraction.py / api/routes/resumes.py for the extraction
-- contract and sync logic that now populate these.
--
-- `confidence`/`evidence`/`source` (added in 2_add_skill_extraction_
-- columns.sql, and `origin` in 3_add_user_skill_origin.sql) are
-- deliberately NOT dropped here -- doing so in the same migration as the
-- code that stops writing them would break a rolling deploy where old
-- app instances (still writing those columns) run alongside the new
-- schema. They're obsolete for the resume flow as of this migration and
-- have no other consumer in the codebase; drop them in a follow-up
-- migration once rollout is confirmed complete.

alter table public.user_skill
    add column if not exists proficiency_level integer,
    add column if not exists proficiency_confidence text;

alter table public.user_skill
    add constraint ck_user_skill_proficiency_level_range
        check (proficiency_level is null or proficiency_level between 0 and 100);

alter table public.user_skill
    add constraint ck_user_skill_proficiency_confidence_values
        check (proficiency_confidence is null or proficiency_confidence in ('low', 'medium', 'high'));
