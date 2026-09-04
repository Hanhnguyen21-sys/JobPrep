import { apiFetch } from "@/lib/api/client";
import type {
  RoadmapGenerationAcceptedResponse,
  RoadmapGenerationStatusResponse,
  RoadmapResponse,
} from "@/types/roadmap";

// Calls POST /roadmaps -- always 202 Accepted now: the backend enqueues a
// background generation (fetch descriptions for up to
// MAX_SELECTED_POSTINGS selected postings, extract skills, then two AI
// calls -- see backend/app/api/routes/roadmaps.py's
// _run_roadmap_generation_task) and returns a task_id immediately rather
// than the roadmap itself. See hooks/useRoadmapGeneration.ts for the
// polling that follows, mirroring hooks/useJobMatch.ts's shape for
// /jobs/match.
export async function createRoadmap(
  jobPostingIds: string[],
): Promise<RoadmapGenerationAcceptedResponse> {
  return apiFetch<RoadmapGenerationAcceptedResponse>("/roadmaps", {
    method: "POST",
    body: JSON.stringify({ job_posting_ids: jobPostingIds }),
  });
}

// Calls GET /roadmaps/status/{taskId} -- polled by useRoadmapGeneration
// after a POST /roadmaps 202 response until `status` reaches a terminal
// state (completed/failed).
export async function getRoadmapGenerationStatus(
  taskId: string,
): Promise<RoadmapGenerationStatusResponse> {
  return apiFetch<RoadmapGenerationStatusResponse>(`/roadmaps/status/${taskId}`);
}

// Calls GET /roadmaps/{id} -- fetches the full roadmap once its
// generation task reports "completed". Also used by app/roadmaps/page.tsx
// for revisiting an existing roadmap from history.
export async function getRoadmap(roadmapId: string): Promise<RoadmapResponse> {
  return apiFetch<RoadmapResponse>(`/roadmaps/${roadmapId}`);
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
