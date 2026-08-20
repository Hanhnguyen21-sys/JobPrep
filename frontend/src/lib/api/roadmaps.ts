import { apiFetch } from "@/lib/api/client";
import type { RoadmapResponse } from "@/types/roadmap";

// Calls POST /roadmaps -- the backend combines the descriptions of the
// (up to MAX_SELECTED_POSTINGS) selected postings into a single AI call
// server-side (see backend/app/services/roadmap.py) and persists the
// result, so this returns the full generated roadmap, not just an id.
// This is the slow, explicitly-triggered call from SelectionBar's
// "Create roadmap" button -- see hooks/useRoadmapGeneration.ts for why
// it's a separate hook from useJobMatch/useJobSelection.
export async function createRoadmap(
  jobPostingIds: string[],
): Promise<RoadmapResponse> {
  return apiFetch<RoadmapResponse>("/roadmaps", {
    method: "POST",
    body: JSON.stringify({ job_posting_ids: jobPostingIds }),
  });
}

// Calls GET /roadmaps -- every roadmap the current user has generated,
// newest first (backend orders by created_at desc already). Used by
// app/roadmaps/page.tsx.
export async function listRoadmaps(): Promise<RoadmapResponse[]> {
  return apiFetch<RoadmapResponse[]>("/roadmaps");
}

// Calls DELETE /roadmaps/{id} -- permanently removes a roadmap the user
// no longer wants in their history. 204 No Content on success; apiFetch
// already returns undefined for 204s, so there's nothing to unwrap.
export async function deleteRoadmap(roadmapId: string): Promise<void> {
  await apiFetch<void>(`/roadmaps/${roadmapId}`, { method: "DELETE" });
}
