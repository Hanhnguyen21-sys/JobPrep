import { apiFetch } from "@/lib/api/client";
import type { TrackedJobResponse, TrackedJobStatus } from "@/types/tracker";

// Calls GET /tracker -- every job the current user has tracked, newest
// first (backend orders by created_at desc). Used by app/tracker/page.tsx.
export async function listTrackedJobs(): Promise<TrackedJobResponse[]> {
  return apiFetch<TrackedJobResponse[]>("/tracker");
}

// Calls POST /tracker -- idempotent server-side (get_or_create_tracked_job),
// so calling this again for a posting that's already tracked just returns
// the existing row (with its current status) rather than creating a
// duplicate or resetting progress. This is the ONLY place a job gets
// tracked from -- see hooks/useJobSelection.ts, which calls it as a side
// effect of the existing Job Match selection checkbox rather than through
// a separate "Add to Tracker" control.
export async function trackJob(jobPostingId: string): Promise<TrackedJobResponse> {
  return apiFetch<TrackedJobResponse>("/tracker", {
    method: "POST",
    body: JSON.stringify({ job_posting_id: jobPostingId }),
  });
}

// Calls PATCH /tracker/{id} -- updates one tracked job's status. Returns
// the full updated row so the caller can resync local state from the
// server's version.
export async function updateTrackedJobStatus(
  trackedJobId: string,
  status: TrackedJobStatus,
): Promise<TrackedJobResponse> {
  return apiFetch<TrackedJobResponse>(`/tracker/${trackedJobId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// Calls DELETE /tracker/{id} -- removes this user's tracking row only;
// the shared job posting is untouched and stays visible/selectable on Job
// Match. 204 No Content on success; apiFetch already returns undefined
// for 204s.
export async function removeTrackedJob(trackedJobId: string): Promise<void> {
  await apiFetch<void>(`/tracker/${trackedJobId}`, { method: "DELETE" });
}
