"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { findMatchingJobs, getMatchStatus } from "@/lib/api/jobs";
import type { JobMatchResponse, TaskStatus } from "@/types/job";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES: TaskStatus[] = ["completed", "partial_failure", "failed"];

// Deliberately its own hook, not folded into useResume -- POST /jobs/match
// is a separate, explicitly-triggered action from resume submission.
//
// Phase 3: /jobs/match itself is now database-only and always fast --
// `result` can come back with freshness "stale" (real data shown
// immediately, a background refresh already running) or "pending"
// (nothing yet). Either way, if a `task_id` comes back, this hook polls
// GET /jobs/match/status/{task_id} until the refresh reaches a terminal
// status, then re-fetches once to pick up whatever's now in the
// database -- `refreshing` is true for exactly that window, distinct
// from `loading` (the initial POST /jobs/match request itself).
export function useJobMatch() {
  const [result, setResult] = useState<JobMatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // True specifically for the "no target_position set yet" 400 the
  // backend returns -- lets the page show a "go submit your resume
  // first" nudge instead of a generic error message.
  const [needsTargetPosition, setNeedsTargetPosition] = useState(false);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  function pollUntilDone(taskId: string) {
    setRefreshing(true);

    async function tick() {
      let status;
      try {
        status = await getMatchStatus(taskId);
      } catch {
        // Polling failure -- stop silently rather than retrying forever;
        // the data already shown (if any) stays as the last known result.
        setRefreshing(false);
        return;
      }

      if (TERMINAL_STATUSES.includes(status.status)) {
        try {
          setResult(await findMatchingJobs());
        } catch {
          // Keep whatever was already shown if this final re-fetch fails.
        }
        setRefreshing(false);
        return;
      }

      pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    }

    pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
  }

  // Doesn't rethrow on failure — `error` is the intended way for the
  // caller to find out something went wrong.
  async function findMatches() {
    setLoading(true);
    setError(null);
    setNeedsTargetPosition(false);

    try {
      const response = await findMatchingJobs();
      setResult(response);
      if (response.freshness !== "fresh" && response.task_id) {
        pollUntilDone(response.task_id);
      }
      return response;
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setNeedsTargetPosition(true);
      } else {
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong finding matching jobs. Try again.";
        setError(message);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { result, loading, refreshing, error, needsTargetPosition, findMatches };
}
