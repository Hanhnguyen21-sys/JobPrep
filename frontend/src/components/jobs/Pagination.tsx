import { Button } from "@/components/ui/Button";

interface PaginationProps {
  page: number;
  totalPages: number;
  totalCount: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
  // True while a page fetch is in flight -- both arrows are disabled so
  // the user can't stack up overlapping requests (see hooks/useJobMatch.ts).
  disabled?: boolean;
}

// Prev/next navigation for the paginated /jobs/match result list. Shows
// both the item range ("16–30 of 507") and the page position ("Page 2 of
// 34"). Renders nothing when there's nothing to page through.
export function Pagination({
  page,
  totalPages,
  totalCount,
  pageSize,
  onPrev,
  onNext,
  disabled = false,
}: PaginationProps) {
  if (totalCount === 0) return null;

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, totalCount);
  const atFirst = page <= 1;
  const atLast = page >= totalPages;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
      <p className="font-mono text-xs text-slate">
        {first}–{last} of {totalCount}
      </p>
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          onClick={onPrev}
          disabled={disabled || atFirst}
          aria-label="Previous page"
        >
          ‹ Prev
        </Button>
        <span className="font-mono text-xs text-slate">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="ghost"
          onClick={onNext}
          disabled={disabled || atLast}
          aria-label="Next page"
        >
          Next ›
        </Button>
      </div>
    </div>
  );
}
