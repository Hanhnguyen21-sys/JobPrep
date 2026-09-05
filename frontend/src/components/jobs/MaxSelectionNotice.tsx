import { MAX_SELECTED_POSTINGS } from "@/types/job";

// Stable id so the disabled JobCard checkboxes can point their
// aria-describedby at this notice -- import MAX_NOTICE_ID from here rather
// than re-typing the string.
export const MAX_NOTICE_ID = "job-selection-max-notice";

// Rendered next to the job list (not only in the sticky SelectionBar) and
// ONLY while the selection is at the cap -- it's the *reason* the
// unchecked checkboxes have gone inert. role="status" makes it a polite
// live region, so a screen reader announces it the moment it appears.
export function MaxSelectionNotice() {
  return (
    <p
      id={MAX_NOTICE_ID}
      role="status"
      className="rounded-md border border-blaze/30 bg-blaze/5 px-3 py-2 text-xs font-medium text-ink"
    >
      {MAX_SELECTED_POSTINGS} is the maximum — deselect one to choose another.
    </p>
  );
}
