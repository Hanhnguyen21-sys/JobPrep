"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { extractSkillsFromResume } from "@/lib/api/resumes";
import type { Skill } from "@/types/skill";

export function useResume() {
  /**
   *  skills    → skills returned from the last successful submission
   *  loading   → is a submission currently in flight?
   *  error     → message from the last failed submission, if any
   */
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Doesn't rethrow on failure — `error` is the intended way for the
  // caller to find out something went wrong. ResumeForm can just
  // `await submitResume(text, targetPosition)` and render `error` without
  // needing its own try/catch.
  async function submitResume(text: string, targetPosition: string) {
    setLoading(true);
    setError(null);

    try {
      const result = await extractSkillsFromResume(text, targetPosition);
      setSkills(result);
      return result;
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong extracting skills. Try again.";
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { skills, loading, error, submitResume };
}
