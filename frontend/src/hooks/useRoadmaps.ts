"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { deleteRoadmap, listRoadmaps } from "@/lib/api/roadmaps";
import type { RoadmapResponse } from "@/types/roadmap";

// Fetches the current user's past roadmaps on mount -- for
// app/roadmaps/page.tsx. Separate from useRoadmapGeneration.ts (creating
// one is a slow, explicitly-triggered POST; listing existing ones is a
// fast GET that should just happen when the page loads), same split as
// useJobMatch vs. useResume.
export function useRoadmaps() {
  const [roadmaps, setRoadmaps] = useState<RoadmapResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Id of the roadmap currently being deleted (at most one at a time,
  // since the page only lets one confirm/delete flow be open) -- lets
  // the UI show "Deleting..." on the right card instead of a single
  // page-wide loading flag.
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    listRoadmaps()
      .then((response) => {
        if (!cancelled) setRoadmaps(response);
      })
      .catch((err) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong loading your roadmaps. Try refreshing.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function removeRoadmap(roadmapId: string) {
    setDeletingId(roadmapId);
    setDeleteError(null);

    try {
      await deleteRoadmap(roadmapId);
      // Drop it from local state directly rather than refetching the
      // whole list -- the DELETE already succeeded, no need for a round
      // trip just to confirm what we already know.
      setRoadmaps((prev) => prev.filter((r) => r.id !== roadmapId));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong deleting that roadmap. Try again.";
      setDeleteError(message);
    } finally {
      setDeletingId(null);
    }
  }

  return {
    roadmaps,
    loading,
    error,
    deletingId,
    deleteError,
    removeRoadmap,
  };
}
