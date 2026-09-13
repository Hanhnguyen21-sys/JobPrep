"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  listTrackedJobs,
  removeTrackedJob,
  updateTrackedJobStatus,
} from "@/lib/api/tracker";
import type { TrackedJobResponse, TrackedJobStatus } from "@/types/tracker";

// Fetches the current user's tracked jobs on mount -- for
// app/tracker/page.tsx. Same fetch-on-mount + optimistic-mutation shape
// as hooks/useRoadmaps.ts.
export function useTracker() {
  const [trackedJobs, setTrackedJobs] = useState<TrackedJobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Id of the entry whose status is currently being saved (at most one
  // at a time, since each row has its own <select>) -- lets the UI
  // disable just that row's control instead of a page-wide flag.
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    listTrackedJobs()
      .then((response) => {
        if (!cancelled) setTrackedJobs(response);
      })
      .catch((err) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong loading your tracker. Try refreshing.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const updateStatus = useCallback(
    async (trackedJobId: string, status: TrackedJobStatus) => {
      setUpdatingId(trackedJobId);
      setUpdateError(null);

      // Optimistic update, reverted on failure -- the status dropdown
      // should feel instant rather than waiting on a round trip.
      let previous: TrackedJobResponse[] = [];
      setTrackedJobs((prev) => {
        previous = prev;
        return prev.map((job) =>
          job.id === trackedJobId ? { ...job, status } : job,
        );
      });

      try {
        const updated = await updateTrackedJobStatus(trackedJobId, status);
        setTrackedJobs((prev) =>
          prev.map((job) => (job.id === trackedJobId ? updated : job)),
        );
      } catch (err) {
        setTrackedJobs(previous);
        const message =
          err instanceof ApiError
            ? err.message
            : "Couldn't update that status. Try again.";
        setUpdateError(message);
      } finally {
        setUpdatingId(null);
      }
    },
    [],
  );

  const removeEntry = useCallback(async (trackedJobId: string) => {
    setDeletingId(trackedJobId);
    setDeleteError(null);

    try {
      await removeTrackedJob(trackedJobId);
      setTrackedJobs((prev) => prev.filter((job) => job.id !== trackedJobId));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't remove that entry. Try again.";
      setDeleteError(message);
    } finally {
      setDeletingId(null);
    }
  }, []);

  return {
    trackedJobs,
    loading,
    error,
    updatingId,
    updateError,
    updateStatus,
    deletingId,
    deleteError,
    removeEntry,
  };
}
