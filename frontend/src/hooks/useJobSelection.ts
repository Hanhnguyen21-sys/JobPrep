"use client";

import { useCallback, useMemo, useState } from "react";
import { MAX_SELECTED_POSTINGS } from "@/types/job";
import type { MatchedJobPosting } from "@/types/job";

// Tracks which matched postings the user has checked -- the User_Job_Selection
// step feeding roadmap generation (POST /roadmaps, see
// hooks/useRoadmapGeneration.ts). Deliberately in-memory frontend state
// only -- nothing here is persisted independently of the roadmap it
// eventually produces (see setup-progress.md's Step 6 note on why there's
// no User_Job_Selection table). `postings` is the current result set,
// passed in so selectedPostings can be derived; the hook doesn't own the
// list itself.
//
// Capped at MAX_SELECTED_POSTINGS (10) -- the same rule
// backend/app/schemas/job.py enforces server-side (both POST /roadmaps
// and POST /jobs/skill-gap). Enforced here too so a user finds out
// they've hit the limit by the 11th checkbox not responding, not by a
// 400 after clicking "Create roadmap" or "Quick prep check".
//
// Selected ids are NOT auto-cleared when `postings` changes underneath this
// hook (e.g. a fresh "Find matching jobs" search) -- that would silently
// drop a user's picks mid-review. Callers that want a clean slate on a new
// search (recommended -- old postings' ids are meaningless once replaced)
// should call `clear()` explicitly after a new result comes back.
export function useJobSelection(postings: MatchedJobPosting[]) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (next.size >= MAX_SELECTED_POSTINGS) {
          // At the cap -- ignore rather than evict an existing pick or
          // silently no-op in a way the caller can't distinguish from "id
          // not found." UI should be disabling unchecked checkboxes at
          // this point anyway (see isMaxed below).
          return prev;
        }
        next.add(id);
      }
      return next;
    });
  }, []);

  const isSelected = useCallback(
    (id: string) => selectedIds.has(id),
    [selectedIds]
  );

  const clear = useCallback(() => setSelectedIds(new Set()), []);

  const selectedPostings = useMemo(
    () => postings.filter((posting) => selectedIds.has(posting.id)),
    [postings, selectedIds]
  );

  return {
    selectedIds,
    isSelected,
    toggle,
    clear,
    selectedPostings,
    selectedCount: selectedIds.size,
    isMaxed: selectedIds.size >= MAX_SELECTED_POSTINGS,
  };
}
