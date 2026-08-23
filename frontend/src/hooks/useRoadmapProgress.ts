"use client";

import { useState } from "react";
import { updateRoadmapProgress } from "@/lib/api/roadmaps";
import type { RoadmapResponse } from "@/types/roadmap";

// Single source of truth for "which action items are checked off" for one
// roadmap, backed by the persisted RoadmapResponse.completed_action_items
// rather than local-only state -- this is what makes checking a box on
// /roadmaps (via RoadmapViewer -> RoadmapPhaseColumn -> PhaseChecklist)
// show up the same way in the Dashboard's ActiveRoadmap summary: both read
// the same field from the same GET /roadmaps response, just at different
// times. Read-only callers (ActiveRoadmap) use completedCount/totalCount
// and never call toggle; RoadmapViewer uses isDone + toggle for the
// interactive checklist.
export function useRoadmapProgress(roadmap: RoadmapResponse) {
  const [completed, setCompleted] = useState(roadmap.completed_action_items);

  function isDone(stepOrder: number, itemIndex: number): boolean {
    return completed[String(stepOrder)]?.includes(itemIndex) ?? false;
  }

  function completedCountForStep(stepOrder: number): number {
    return completed[String(stepOrder)]?.length ?? 0;
  }

  async function toggle(stepOrder: number, itemIndex: number) {
    const done = !isDone(stepOrder, itemIndex);
    const key = String(stepOrder);
    const previous = completed;

    // Optimistic update -- reverted if the request fails.
    const nextForStep = done
      ? [...(completed[key] ?? []), itemIndex]
      : (completed[key] ?? []).filter((index) => index !== itemIndex);
    setCompleted({ ...completed, [key]: nextForStep });

    try {
      const confirmed = await updateRoadmapProgress(roadmap.id, stepOrder, itemIndex, done);
      setCompleted(confirmed);
    } catch {
      setCompleted(previous);
    }
  }

  const totalCount = roadmap.steps.reduce(
    (sum, step) => sum + step.action_items.length,
    0,
  );
  const completedCount = Object.values(completed).reduce(
    (sum, indices) => sum + indices.length,
    0,
  );

  return { isDone, toggle, completedCountForStep, completedCount, totalCount };
}
