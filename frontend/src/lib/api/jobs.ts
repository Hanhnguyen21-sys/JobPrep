import { apiFetch } from "@/lib/api/client";
import type { JobMatchResponse, JobMatchStatusResponse } from "@/types/job";

// Calls POST /jobs/match -- reads target_position from the user's saved
// profile server-side, so nothing needs to be sent in the body.
// Database-only and always fast now (Phase 3): it returns whatever's
// already in the database immediately (freshness "fresh"/"stale"/
// "pending") and, if the data isn't fresh, enqueues a background refresh
// rather than doing the live ATS+OpenAI pull itself -- see
// hooks/useJobMatch.ts for the polling that follows a non-fresh response.
export async function findMatchingJobs(): Promise<JobMatchResponse> {
  return apiFetch<JobMatchResponse>("/jobs/match", { method: "POST" });
}

// Calls GET /jobs/match/status/{taskId} -- polled by useJobMatch after a
// "stale"/"pending" POST /jobs/match response until the enqueued
// background refresh reaches a terminal status.
export async function getMatchStatus(taskId: string): Promise<JobMatchStatusResponse> {
  return apiFetch<JobMatchStatusResponse>(`/jobs/match/status/${taskId}`);
}
