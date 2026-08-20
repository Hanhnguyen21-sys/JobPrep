"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { createRoadmap } from "@/lib/api/roadmaps";
import type { RoadmapResponse } from "@/types/roadmap";

// Deliberately its own hook, not folded into useJobMatch or
// useJobSelection -- POST /roadmaps is a separate, explicitly-triggered,
// much slower request (combines every selected posting's description into
// one AI call server-side) than either finding matches or toggling a
// checkbox, so it needs its own loading/error state. Mirrors
// hooks/useJobMatch.ts's shape.
export function useRoadmapGeneration() {
  const [roadmap, setRoadmap] = useState<RoadmapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate(jobPostingIds: string[]) {
    setLoading(true);
    setError(null);

    try {
      const response = await createRoadmap(jobPostingIds);
      setRoadmap(response);
      return response;
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong generating a roadmap. Try again.";
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  function clear() {
    setRoadmap(null);
    setError(null);
  }

  return { roadmap, loading, error, generate, clear };
}
