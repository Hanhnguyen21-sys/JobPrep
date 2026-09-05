import { apiFetch } from "@/lib/api/client";
import { DEFAULT_PAGE_SIZE } from "@/types/job";
import type { JobMatchResponse, JobMatchStatusResponse } from "@/types/job";

// Calls POST /jobs/match -- reads target_position from the user's saved
// profile server-side, so nothing needs to be sent in the body.
// Database-only and always fast now (Phase 3): it returns whatever's
// already in the database immediately (freshness "fresh"/"stale"/
// "pending") and, if the data isn't fresh, enqueues a background refresh
// rather than doing the live ATS+OpenAI pull itself -- see
// hooks/useJobMatch.ts for the polling that follows a non-fresh response.
//
// `page` is 1-indexed. Only one page's worth of postings comes back;
// paging calls this again with the next `page` rather than fetching
// everything and slicing client-side.
export async function findMatchingJobs(
  page = 1,
  pageSize = DEFAULT_PAGE_SIZE,
): Promise<JobMatchResponse> {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return apiFetch<JobMatchResponse>(`/jobs/match?${query}`, { method: "POST" });
}

// Calls GET /jobs/match/status/{taskId} -- polled by useJobMatch after a
// "stale"/"pending" POST /jobs/match response until the enqueued
// background refresh reaches a terminal status.
export async function getMatchStatus(taskId: string): Promise<JobMatchStatusResponse> {
  return apiFetch<JobMatchStatusResponse>(`/jobs/match/status/${taskId}`);
}
