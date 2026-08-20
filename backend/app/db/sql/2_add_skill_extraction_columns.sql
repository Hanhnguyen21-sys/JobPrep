-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds the columns resume skill extraction needs on top of the bare
-- `skills` / `user_skill` tables created in 1_create_users_and_trigger.sql.

-- Every skill belongs to a category. Using a temporary default so this is
-- safe to run even if you've already inserted test rows, then dropping it
-- so future inserts must specify category explicitly (matches the
-- SQLAlchemy model, which marks it nullable=False with no default).
alter table public.skills
    add column if not exists category text not null default 'technical';

alter table public.skills
    alter column category drop default;

create index if not exists ix_skills_category on public.skills (category);

-- Per-user, per-extraction context for why this skill got linked to this
-- user. Nullable — a skill could get linked another way later (e.g. the
-- user manually adding one) without this context existing.
alter table public.user_skill
    add column if not exists confidence text,
    add column if not exists evidence text,
    add column if not exists source text;
