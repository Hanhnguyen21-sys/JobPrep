"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { extractSkillsFromResume, extractSkillsFromResumeFile } from "@/lib/api/resumes";
import type { Skill } from "@/types/skill";

// Both submit paths share this one skills/loading/error state -- the
// result UI (ExtractedSkillsList, on app/resume/page.tsx) reads the same
// `skills` regardless of whether they came from pasted text or an OCR'd
// image, so it never needs to know which one ran.
export function useResume() {
  /**
   *  skills    → skills returned from the last successful submission
   *  loading   → is a submission currently in flight?
   *  error     → message from the last failed submission, if any
   */
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toErrorMessage(err: unknown): string {
    return err instanceof ApiError
      ? err.message
      : "Something went wrong extracting skills. Try again.";
  }

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
      setError(toErrorMessage(err));
      return null;
    } finally {
      setLoading(false);
    }
  }

  // Same contract as submitResume, just OCR'd first server-side (image or
  // PDF) -- see lib/api/resumes.ts's extractSkillsFromResumeFile.
  async function submitResumeFile(file: File, targetPosition: string) {
    setLoading(true);
    setError(null);

    try {
      const result = await extractSkillsFromResumeFile(file, targetPosition);
      setSkills(result);
      return result;
    } catch (err) {
      setError(toErrorMessage(err));
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { skills, loading, error, submitResume, submitResumeFile };
}
