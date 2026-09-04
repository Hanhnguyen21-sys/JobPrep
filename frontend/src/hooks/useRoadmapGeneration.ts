"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  createRoadmap,
  getRoadmap,
  getRoadmapGenerationStatus,
} from "@/lib/api/roadmaps";
import type { RoadmapResponse, RoadmapTaskStatus } from "@/types/roadmap";

const POLL_INTERVAL_MS = 2000;
// ~5 minutes -- generation can involve up to MAX_SELECTED_POSTINGS
// sequential external description fetches plus two LLM calls
// server-side (see backend/app/api/routes/roadmaps.py's
// _run_roadmap_generation_task), legitimately slower than a typical
// /jobs/match refresh, so this needs a generous ceiling, not zero.
const MAX_POLL_ATTEMPTS = 150;
const TERMINAL_STATUSES: RoadmapTaskStatus[] = ["completed", "failed"];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Deliberately its own hook, not folded into useJobMatch or
// useJobSelection -- POST /roadmaps is a separate, explicitly-triggered
// action. Unlike useJobMatch (which polls in the background and lets the
// caller move on immediately after the initial request), `generate()`
// here awaits the whole enqueue -> poll -> fetch flow before resolving --
// the "Create roadmap" button's loading state is meant to cover the
// entire generation end to end, same UX contract as before this became a
// background task server-side (see backend/app/api/routes/roadmaps.py),
// just no longer implemented as one single blocking request.
export function useRoadmapGeneration() {
  const [roadmap, setRoadmap] = useState<RoadmapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function generate(jobPostingIds: string[]) {
    setLoading(true);
    setError(null);

    try {
      const accepted = await createRoadmap(jobPostingIds);

      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await sleep(POLL_INTERVAL_MS);
        if (!mountedRef.current) return null;

        const taskStatus = await getRoadmapGenerationStatus(accepted.task_id);
        if (!TERMINAL_STATUSES.includes(taskStatus.status)) continue;

        if (taskStatus.status === "failed" || !taskStatus.roadmap_id) {
          setError(
            taskStatus.error_summary ??
              "Couldn't generate a roadmap from these postings. Try again.",
          );
          return null;
        }

        const full = await getRoadmap(taskStatus.roadmap_id);
        if (mountedRef.current) setRoadmap(full);
        return full;
      }

      // Bounded ceiling reached -- a stuck task (e.g. the server
      // restarted mid-generation, see the durability caveat on
      // backend/app/models/roadmap_generation_task.py) must not poll
      // this component forever with no way out.
      setError(
        "Generating this roadmap is taking longer than expected. Try again shortly.",
      );
      return null;
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong generating a roadmap. Try again.";
      if (mountedRef.current) setError(message);
      return null;
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }

  function clear() {
    setRoadmap(null);
    setError(null);
  }

  return { roadmap, loading, error, generate, clear };
}
