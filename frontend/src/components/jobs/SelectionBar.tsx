import { Button } from "@/components/ui/Button";
import { MAX_SELECTED_POSTINGS } from "@/types/job";

interface SelectionBarProps {
  selectedCount: number;
  onClear: () => void;
  onCreateRoadmap: () => void;
  // True while POST /roadmaps is in flight (hooks/useRoadmapGeneration.ts)
  // -- disables both actions so a slow AI call can't be double-submitted
  // or have its selection yanked out from under it mid-request.
  generating?: boolean;
}

// Surfaces the current User_Job_Selection count and the action it feeds:
// the AI-backed "Create roadmap" (POST /roadmaps). Hidden entirely when
// nothing's selected rather than shown disabled, so it doesn't compete
// for attention before there's anything to act on.
export function SelectionBar({
  selectedCount,
  onClear,
  onCreateRoadmap,
  generating = false,
}: SelectionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="sticky bottom-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <span className="text-sm font-medium">
        {selectedCount} job{selectedCount === 1 ? "" : "s"} selected
        {selectedCount >= MAX_SELECTED_POSTINGS ? " (max)" : ""}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onClear}
          disabled={generating}
          className="text-sm text-zinc-500 underline hover:text-zinc-700 disabled:opacity-50 disabled:pointer-events-none dark:hover:text-zinc-300"
        >
          Clear
        </button>
        <Button onClick={onCreateRoadmap} disabled={generating}>
          {generating ? "Generating..." : "Create roadmap"}
        </Button>
      </div>
    </div>
  );
}
