import { JobCard } from "@/components/jobs/JobCard";
import type { MatchedJobPosting } from "@/types/job";

interface JobListProps {
  postings: MatchedJobPosting[];
  isSelected: (id: string) => boolean;
  onToggle: (posting: MatchedJobPosting) => void;
  // See JobCard's `disabled` -- true once the selection cap is reached.
  isMaxed?: boolean;
  // Total across every page of the match set. Lets an empty `postings`
  // mean two different things: no matches at all, vs. a page past the
  // end. Defaults to postings.length for callers that don't paginate.
  totalCount?: number;
}

export function JobList({
  postings,
  isSelected,
  onToggle,
  isMaxed = false,
  totalCount,
}: JobListProps) {
  if (postings.length === 0) {
    const noMatchesAtAll = (totalCount ?? postings.length) === 0;
    return (
      <p className="text-sm text-slate">
        {noMatchesAtAll
          ? "No postings matched your target position this time — try a broader title, or check back later as more get ingested."
          : "No postings on this page — go back a page."}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {postings.map((posting) => {
        const selected = isSelected(posting.id);
        return (
          <JobCard
            key={posting.id}
            posting={posting}
            selected={selected}
            onToggle={onToggle}
            disabled={isMaxed && !selected}
          />
        );
      })}
    </div>
  );
}
