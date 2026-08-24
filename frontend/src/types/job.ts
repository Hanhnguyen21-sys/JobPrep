// Mirrors backend/app/schemas/job.py -- keep these two in sync by hand for
// now (no shared codegen yet), same convention as types/skill.ts.
import type { SkillCategory } from "@/types/skill";

// Canonical home for the "at most N selected postings" rule -- mirrors
// schemas/job.py's MAX_SELECTED_POSTINGS. Feeds the full roadmap
// (types/roadmap.ts imports this rather than redefining it).
export const MAX_SELECTED_POSTINGS = 10;

export interface MatchedJobPosting {
  id: string;
  company_name: string;
  title: string;
  location: string | null;
  url: string | null;
}

export type RequirementLevel = "required" | "preferred";

export interface SkillGapItem {
  skill_id: string;
  name: string;
  category: SkillCategory;
  requirement_level: RequirementLevel;
  user_has: boolean;
}

// See backend/app/schemas/job.py's DataFreshness/TaskStatus for the
// meaning of each value -- Phase 3 of the /jobs/match latency work
// (database-only + non-blocking + background-refresh polling).
export type DataFreshness = "fresh" | "stale" | "pending";
export type TaskStatus = "queued" | "running" | "completed" | "partial_failure" | "failed";

export interface JobMatchResponse {
  target_position: string;
  postings: MatchedJobPosting[];
  skill_gap: SkillGapItem[];
  freshness: DataFreshness;
  // Set whenever a background refresh was enqueued (freshness is
  // "stale" or "pending") -- poll GET /jobs/match/status/{task_id}.
  task_id: string | null;
}

export interface JobMatchStatusResponse {
  task_id: string;
  status: TaskStatus;
  data_freshness: DataFreshness;
  last_updated_at: string | null;
  error_summary: string | null;
}
