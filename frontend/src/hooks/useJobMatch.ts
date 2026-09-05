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
//
// Pagination: the backend returns one page of the match set at a time.
// `findMatches()` runs a new search (always page 1); `goToPage(n)`
// re-fetches page n from the backend (not a client-side slice).
// `pageLoading` covers an in-flight page nav, kept separate from
// `loading` so the page can show a subtler indicator for it. Every fetch
// carries a sequence number (`reqSeq`) and only the newest one is
// allowed to write state -- so rapid arrow-clicking can't let a slow
// page-2 response land after a fast page-3 response.
export function useJobMatch() {
  const [result, setResult] = useState<JobMatchResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // True specifically for the "no target_position set yet" 400 the
  // backend returns -- lets the page show a "go submit your resume
  // first" nudge instead of a generic error message.
  const [needsTargetPosition, setNeedsTargetPosition] = useState(false);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Monotonic id for the most recently *started* fetch. A response whose
  // id != reqSeq.current has been superseded and must not touch state.
  const reqSeq = useRef(0);
  // Latest page actually being viewed -- read by the poll's terminal
  // re-fetch so it reloads whatever page the user is on now, even if
  // they navigated while the background refresh was running.
  const pageRef = useRef(1);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
      // Bump so any fetch/poll still in flight when we unmount is ignored.
      reqSeq.current += 1;
    };
  }, []);

  function applyPage(next: number) {
    pageRef.current = next;
    setPage(next);
  }

  function pollUntilDone(taskId: string) {
    setRefreshing(true);

    async function tick() {
      let status;
      try {
        status = await getMatchStatus(taskId);
      } catch {
        // Polling failure -- stop silently rather than retrying forever;
        // the data already shown (if any) stays as the last known result.
        if (mountedRef.current) setRefreshing(false);
        return;
      }

      if (TERMINAL_STATUSES.includes(status.status)) {
        // Refresh finished -- reload the page the user is currently on.
        // Take a fresh sequence number so this supersedes (and is
        // superseded by) any manual navigation racing with it.
        const seq = ++reqSeq.current;
        try {
          const fresh = await findMatchingJobs(pageRef.current);
          if (mountedRef.current && seq === reqSeq.current) {
            setResult(fresh);
            applyPage(fresh.page);
          }
        } catch {
          // Keep whatever was already shown if this final re-fetch fails.
        }
        if (mountedRef.current) setRefreshing(false);
        return;
      }

      pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    }

    pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
  }

  async function fetchPage(
    targetPage: number,
    { isNewSearch }: { isNewSearch: boolean },
  ): Promise<JobMatchResponse | null> {
    const seq = ++reqSeq.current;
    if (isNewSearch) {
      setLoading(true);
      setError(null);
      setNeedsTargetPosition(false);
      // A new search invalidates any refresh-poll from the previous one.
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
      setRefreshing(false);
    } else {
      setPageLoading(true);
    }

    try {
      const response = await findMatchingJobs(targetPage);
      if (seq !== reqSeq.current) return null; // superseded by a newer fetch

      setResult(response);
      applyPage(response.page);
      if (response.freshness !== "fresh" && response.task_id) {
        pollUntilDone(response.task_id);
      }
      return response;
    } catch (err) {
      if (seq !== reqSeq.current) return null;
      if (isNewSearch && err instanceof ApiError && err.status === 400) {
        setNeedsTargetPosition(true);
      } else {
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong finding matching jobs. Try again.",
        );
      }
      return null;
    } finally {
      if (seq === reqSeq.current) {
        setLoading(false);
        setPageLoading(false);
      }
    }
  }

  // Doesn't rethrow on failure -- `error` / `needsTargetPosition` are the
  // intended way for the caller to find out something went wrong. Always
  // starts a new search from page 1.
  function findMatches(): Promise<JobMatchResponse | null> {
    return fetchPage(1, { isNewSearch: true });
  }

  function goToPage(next: number): void {
    if (next < 1) return;
    if (result && next > result.total_pages) return;
    // Ignore spam-clicks while a page fetch is already running. A
    // background refresh (`refreshing`) does NOT block paging -- its
    // terminal re-fetch reads pageRef, so it lands on whatever page the
    // user has moved to; reqSeq keeps the last write authoritative.
    if (loading || pageLoading) return;
    void fetchPage(next, { isNewSearch: false });
  }

  return {
    result,
    page,
    loading,
    pageLoading,
    refreshing,
    error,
    needsTargetPosition,
    findMatches,
    goToPage,
  };
}
