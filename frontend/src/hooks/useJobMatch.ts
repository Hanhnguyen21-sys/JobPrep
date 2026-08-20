"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { findMatchingJobs } from "@/lib/api/jobs";
import type { JobMatchResponse } from "@/types/job";

// Deliberately its own hook, not folded into useResume -- POST /jobs/match
// is a separate, explicitly-triggered, and much slower request (live
// Greenhouse/Lever fetch + AI extraction) than resume submission, so it
// needs its own loading/error state rather than reusing useResume's.
export function useJobMatch() {
  const [result, setResult] = useState<JobMatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // True specifically for the "no target_position set yet" 400 the
  // backend returns -- lets the page show a "go submit your resume
  // first" nudge instead of a generic error message.
  const [needsTargetPosition, setNeedsTargetPosition] = useState(false);

  async function findMatches() {
    setLoading(true);
    setError(null);
    setNeedsTargetPosition(false);

    try {
      const response = await findMatchingJobs();
      setResult(response);
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

  return { result, loading, error, needsTargetPosition, findMatches };
}
