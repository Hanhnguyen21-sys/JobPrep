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
    <div className="sticky bottom-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-line bg-surface px-4 py-3 shadow-lg shadow-black/5">
      <span className="font-mono text-sm font-medium text-ink">
        {selectedCount} job{selectedCount === 1 ? "" : "s"} selected
        {selectedCount >= MAX_SELECTED_POSTINGS ? " (max)" : ""}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={onClear} disabled={generating}>
          Clear
        </Button>
        <Button onClick={onCreateRoadmap} disabled={generating}>
          {generating ? "Generating..." : "Create roadmap"}
        </Button>
      </div>
    </div>
  );
}
