-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Adds `origin` to user_skill, so a resume resubmission can safely sync
-- (add/remove) only the rows *it* created, without touching rows created
-- some other way later (e.g. a future "manually add a skill" feature).

alter table public.user_skill
    add column if not exists origin text not null default 'resume';
