import { apiFetch } from "@/lib/api/client";
import type { JobMatchResponse } from "@/types/job";

// Calls POST /jobs/match -- reads target_position from the user's saved
// profile server-side, so nothing needs to be sent in the body. This is
// the slow, explicitly-triggered call (live ATS fetch + filter + extract
// + skill-gap compare); see hooks/useJobMatch.ts for why it's a separate
// action from resume submission rather than chained automatically.
export async function findMatchingJobs(): Promise<JobMatchResponse> {
  return apiFetch<JobMatchResponse>("/jobs/match", { method: "POST" });
}
