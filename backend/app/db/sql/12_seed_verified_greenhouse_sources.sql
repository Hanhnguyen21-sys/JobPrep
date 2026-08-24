-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Seeds five verified Greenhouse company sources into `companies`, so
-- ingestion/runner.py's tracked-company query (_get_tracked_companies)
-- has real sources to read beyond whatever a live ingestion run happened
-- to create on its own via _get_or_create_company.
--
-- Idempotent: uses the same (ats_platform, ats_identifier) uniqueness
-- already enforced by uq_companies_platform_identifier
-- (4_create_companies_and_job_postings.sql). Re-running this file updates
-- only `name`/`career_page_url` for a row that already exists (safe,
-- display-only metadata) -- it never touches `id`/`created_at`, and never
-- deletes or otherwise touches any other row. GitLab, Coinbase, or any
-- other company already present in the table is left exactly as-is.

insert into public.companies (name, ats_platform, ats_identifier, career_page_url)
values
    ('Cloudflare', 'greenhouse', 'cloudflare', 'https://job-boards.greenhouse.io/cloudflare'),
    ('Scale AI', 'greenhouse', 'scaleai', 'https://job-boards.greenhouse.io/scaleai'),
    ('Anduril Industries', 'greenhouse', 'andurilindustries', 'https://job-boards.greenhouse.io/andurilindustries'),
    ('Zipline', 'greenhouse', 'flyzipline', 'https://job-boards.greenhouse.io/flyzipline'),
    ('SpaceX', 'greenhouse', 'spacex', 'https://job-boards.greenhouse.io/spacex')
on conflict (ats_platform, ats_identifier) do update
set
    name = excluded.name,
    career_page_url = excluded.career_page_url;
