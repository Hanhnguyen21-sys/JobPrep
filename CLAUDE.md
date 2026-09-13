# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout

Monorepo with two independent apps that talk over HTTP:

- `backend/` — FastAPI + SQLAlchemy (Python 3.11+, uses `X | None` union syntax)
- `frontend/` — Next.js 16 (App Router) + React 19 + Tailwind v4, talks to the backend via `NEXT_PUBLIC_API_URL`

## Commands

### Backend (run from `backend/`, venv active)

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000   # dev server, http://localhost:8000/docs
pytest                                        # full suite (pytest.ini: pythonpath=., testpaths=tests)
pytest tests/api/test_jobs_route.py           # single file
pytest tests/api/test_jobs_route.py::test_fresh_data_returns_immediately_without_enqueuing  # single test
python -m app.ingestion.runner                # manual full ingestion run (same entry point as the cron job)
python -m app.taxonomy.esco --rebuild         # rebuild the committed ESCO skill taxonomy JSON (network, build-time only)
python -m tests.benchmarks.run_benchmark --label "some-label"  # local integration benchmark (see below)
```

There is no Alembic migration chain despite `alembic` being in `requirements.txt` and the README mentioning `alembic stamp head`. Schema changes are hand-written, sequentially numbered SQL files in `backend/app/db/sql/` (`1_create_users_and_trigger.sql`, `2_...`, etc.), applied manually via the Supabase SQL Editor. When changing the schema: add the next-numbered file, don't edit past ones, and update the corresponding SQLAlchemy model in `app/models/`.

### Frontend (run from `frontend/`)

```bash
npm run dev     # http://localhost:3000
npm run build
npm run lint     # eslint
```

No frontend test runner is configured.

## Environment

Backend needs a `.env` (`app/core/config.py`, `Settings`) with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL`, `OPENAI_API_KEY`, `CORS_ORIGINS`. No `.env.example` exists — check with the user before assuming a value.

Frontend needs `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`.

The `.github/workflows/*.yml` cron job (daily ingestion) and `backend/scripts/run_ingestion.sh` (local cron, hardcoded absolute path) both just invoke `python -m app.ingestion.runner`.

## Backend architecture

### Auth

Supabase Auth issues the JWT; the frontend never sends credentials to this backend. `app/api/dependencies.py:get_current_user` decodes the bearer token via `app/core/security.py:decode_supabase_token` (fetches Supabase's JWKS, verifies ES256), then looks up/lazily-creates the matching `app/models/user.py:User` row (a Postgres trigger — `db/sql/1_create_users_and_trigger.sql` — normally creates it on signup; the lazy path is a fallback for the rare race). Every protected route depends on `get_current_user`.

### Job ingestion pipeline (`app/ingestion/`)

Postings come from parsing the public SimplifyJobs internship-listing README on GitHub (`app/ingestion/readme.py:discover_postings`) — **not** from the Greenhouse/Lever ATS APIs anymore. `app/ingestion/greenhouse.py` and `app/ingestion/lever.py` are legacy: still present and still covered by `tests/ingestion/test_ats_fetch.py` and the benchmark harness, but no longer called from `app/ingestion/runner.py` or any route.

`app/ingestion/runner.py` has two entry points that share the same upsert logic (`_sync_discovered_postings`):
- `run_ingestion()` — the cron/scheduled path: discovers everything, upserts `Company`/`JobPosting`, marks postings not seen in this run `is_active=False` (never deletes, to preserve roadmap history).
- `run_targeted_ingestion(db, desired_position, ...)` — called synchronously from within a background task kicked off by `POST /jobs/match`; filters discovered postings by a fuzzy title match (`app/ingestion/query_normalization.py:title_matches_query`, a hand-kept token/synonym table, not embeddings) before upserting.

Job matching is **cache-then-refresh, never blocking**: `POST /jobs/match` checks `JobSearchCache` freshness (`FRESHNESS_MINUTES = 60`); if stale/missing it enqueues a `JobSearchTask` (deduped per cache_key by a partial unique DB index, not application code — see `app/models/job_search_task.py`) via FastAPI `BackgroundTasks`, and returns immediately with whatever data already exists (`freshness: "fresh" | "stale" | "pending"`) plus a `task_id`. The frontend polls `GET /jobs/match/status/{task_id}` until terminal, then re-calls `POST /jobs/match`. `POST /roadmaps` follows the identical accepted-now/poll-status/fetch-result shape via `RoadmapGenerationTask`, except that task is scoped per-user (job search tasks are global/shared across users since job postings themselves are global data).

Both background-task tables (`JobSearchTask`, `RoadmapGenerationTask`) run via in-process `BackgroundTasks`, not a durable worker (Celery/RQ/ARQ) — a server restart mid-task silently strands it at `"running"` forever. Documented as an accepted tradeoff in both models' docstrings; revisit only if ingestion volume/reliability requirements grow.

### Skills pipeline

Two independent extraction paths feed the same `Skill`/`user_skill`/`job_posting_skill` tables:
1. **Resume → skills**: `app/services/skill_extraction.py` (OpenAI, `gpt-4o-mini`) extracts technical + soft skills with proficiency from resume text (pasted or OCR'd via `app/services/resume_ocr.py`, which renders PDFs to images first since Pillow alone can't OCR a PDF). `app/api/routes/resumes.py:_sync_resume_skills` reconciles the result into `user_skill`, guarded by a Postgres advisory lock (`pg_advisory_xact_lock`) keyed on the user so concurrent submissions can't race.
2. **Job description → required skills**: `app/services/job_skill_extraction.py` extracts required/preferred skills from a posting's description, applied via `app/ingestion/runner.py:sync_job_posting_skills_batch` / `_apply_job_skill_extraction`. Only runs when the description's hash (`hash_description`) actually changed, to avoid re-billing the LLM.

`app/taxonomy/` (ESCO + spaCy `PhraseMatcher`) is a separate, purely rule-based skill-name matcher — no OpenAI call, no network at runtime — built from a JSON file (`esco_taxonomy.json`) that's regenerated offline via `python -m app.taxonomy.esco --rebuild` and committed, not built per-request.

`Skill.category` ("technical"/"soft") is a property of the skill itself; per-user specifics (`proficiency_level`, `proficiency_confidence`, `origin`) live on the `user_skill` join table. Job-posting-derived skills are always recorded as `"technical"` regardless of the skill's real nature — the required/preferred split is what matters there, not technical/soft (see `_apply_job_skill_extraction`'s comment).

### Roadmap generation

`app/services/roadmap.py` (OpenAI) turns a precomputed skill gap (aggregated required/preferred skills across the user's selected postings, cross-referenced against the user's own skills — computed in `app/api/routes/roadmaps.py:_build_skill_gap`, not by the model) into one combined roadmap. Roadmap rows carry a legacy-shape adapter (`_legacy_overview`/`_legacy_step` in `app/api/routes/roadmaps.py`) so older rows generated before a schema/prompt change still render correctly.

### Response-shape conventions worth knowing before touching a route

- Error summaries returned to the client are always sanitized to just the exception's type name (e.g. `f"{type(exc).__name__} during ingestion"`), never `str(exc)` — avoids leaking secrets/paths through a public status field.
- Pagination (`app/api/routes/jobs.py`) is done in Python over the full fuzzy-matched result set, not SQL `LIMIT`/`OFFSET` — the title-fuzzy-match filter itself already has to run in Python.

## Frontend architecture

- `src/lib/supabase/client.ts` / `server.ts` — Supabase clients for Client Components vs. Server Components/Actions respectively; keep them separate rather than sharing one instance.
- `src/proxy.ts` + `src/lib/supabase/proxy.ts` (`updateSession`) — the Next.js middleware; gates `/dashboard`, `/resume`, `/jobs`, `/roadmaps`, `/tracker` behind a Supabase session, redirecting to `/login?next=...`. Nothing may run between `createServerClient(...)` and `supabase.auth.getUser()` in there (breaks token refresh) — see the inline comment.
- `src/lib/api/client.ts` (`apiFetch`) — shared fetch wrapper all of `lib/api/*.ts` use; attaches the Supabase access token as a bearer header and normalizes FastAPI's `{"detail": "..."}` error bodies into `ApiError`. Skips setting `Content-Type` for `FormData` bodies (resume file upload) so the browser can set its own multipart boundary.
- Data fetching is hook-based (`src/hooks/*`), one hook per backend resource (`useJobMatch`, `useRoadmapGeneration`, `useResume`, etc.), each wrapping the matching `lib/api/*.ts` module — follow that pairing when adding a new backend endpoint.
- `frontend/AGENTS.md` (pulled in via `frontend/CLAUDE.md`) is auto-generated/rewritten by `next dev` itself — don't hand-edit its content, just let it get committed if it shows as a diff.

## Testing conventions (backend)

No `conftest.py` / shared fixtures. Route and service tests call the Python functions directly (not `TestClient`/HTTP), passing a `unittest.mock.MagicMock()` for `db` and asserting on what was called against it. For routes using `BackgroundTasks`, tests pass a real `fastapi.BackgroundTasks()` instance and assert on `.add_task()` calls rather than letting the task run (it only executes after a real ASGI response is sent, so it never fires in these tests). `tests/benchmarks/` is a standalone local-integration benchmark harness (real DB, simulated ATS/OpenAI latency) for comparing ingestion performance across phases — not part of the `pytest` suite's correctness checks.
