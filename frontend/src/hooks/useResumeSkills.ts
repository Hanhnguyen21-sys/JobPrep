"use client";

import { useEffect, useState } from "react";
import { getResumeSkills } from "@/lib/api/resumes";
import type { Skill } from "@/types/skill";

// Fetches the current user's already-linked resume skills on mount --
// same fetch-on-mount shape as useCurrentUser/useRoadmaps. Distinct from
// useResume, which only ever holds skills right after a fresh
// submission; this is for showing what's already on file (the
// Dashboard's skills section) without requiring the user to resubmit.
export function useResumeSkills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    getResumeSkills()
      .then((result) => {
        if (!cancelled) setSkills(result);
      })
      .catch(() => {
        // Non-critical for the dashboard -- section just renders empty.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { skills, loading };
}
