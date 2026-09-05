"use client";

import { useCallback, useMemo, useState } from "react";
import { MAX_SELECTED_POSTINGS } from "@/types/job";
import type { MatchedJobPosting } from "@/types/job";

// Tracks which matched postings the user has checked -- the User_Job_Selection
// step feeding roadmap generation (POST /roadmaps, see
// hooks/useRoadmapGeneration.ts). Deliberately in-memory frontend state
// only -- nothing here is persisted independently of the roadmap it
// eventually produces (see setup-progress.md's Step 6 note on why there's
// no User_Job_Selection table).
//
// Stores the full posting object per id (a Map, not just a Set of ids)
// so a selection SURVIVES paging: /jobs/match only returns one page at a
// time, so once the user moves to page 2 the page-1 postings are no
// longer in any list this hook could re-derive them from. selectedCount
// / isMaxed therefore reflect the cross-page total, and selectedPostings
// carries every pick forward to POST /roadmaps regardless of which page
// it was made on.
//
// Capped at MAX_SELECTED_POSTINGS -- the same rule
// backend/app/schemas/job.py enforces server-side (POST /roadmaps via
// schemas/roadmap.py). Enforced here too so a user finds out they've hit
// the limit by the 11th checkbox not responding (+ the MaxSelectionNotice
// banner), not by a 400 after clicking "Create roadmap".
//
// Selections are NOT cleared automatically -- callers that want a clean
// slate on a new "Find matching jobs" search (recommended -- old
// postings' ids are meaningless once replaced) must call `clear()`
// explicitly after the new result comes back. Paging must NOT clear.
export function useJobSelection() {
  const [selected, setSelected] = useState<Map<string, MatchedJobPosting>>(
    new Map(),
  );

  const toggle = useCallback((posting: MatchedJobPosting) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(posting.id)) {
        next.delete(posting.id);
      } else {
        if (next.size >= MAX_SELECTED_POSTINGS) {
          // At the cap -- ignore rather than evict an existing pick. The
          // UI should be disabling unchecked checkboxes at this point
          // anyway (see isMaxed below); this is the backstop.
          return prev;
        }
        next.set(posting.id, posting);
      }
      return next;
    });
  }, []);

  const isSelected = useCallback((id: string) => selected.has(id), [selected]);

  const clear = useCallback(() => setSelected(new Map()), []);

  const selectedPostings = useMemo(
    () => Array.from(selected.values()),
    [selected],
  );

  return {
    isSelected,
    toggle,
    clear,
    selectedPostings,
    selectedCount: selected.size,
    isMaxed: selected.size >= MAX_SELECTED_POSTINGS,
  };
}
