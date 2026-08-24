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

// Calls PATCH /roadmaps/{id}/progress -- checks or unchecks one action
// item on one step. Returns the roadmap's full updated
// completed_action_items map (not just the one item) so the caller can
// resync local state directly from the server's version rather than
// trusting its own optimistic guess. See hooks/useRoadmapProgress.ts.
//
// Sends `interacted_at` (this moment, client-side) so the backend can tell
// a genuinely newer interaction apart from an older request that happens
// to arrive/resolve later -- see repositories/roadmaps.py's
// set_action_item_done. Whichever interaction actually has the latest
// timestamp wins the "current phase" pointer, regardless of network
// ordering.
export async function updateRoadmapProgress(
  roadmapId: string,
  stepOrder: number,
  itemIndex: number,
  done: boolean,
): Promise<{ completedActionItems: Record<string, number[]>; lastInteractedStepOrder: number | null }> {
  const response = await apiFetch<{
    completed_action_items: Record<string, number[]>;
    last_interacted_step_order: number | null;
  }>(`/roadmaps/${roadmapId}/progress`, {
    method: "PATCH",
    body: JSON.stringify({
      step_order: stepOrder,
      item_index: itemIndex,
      done,
      interacted_at: new Date().toISOString(),
    }),
  });
  return {
    completedActionItems: response.completed_action_items,
    lastInteractedStepOrder: response.last_interacted_step_order,
  };
}
