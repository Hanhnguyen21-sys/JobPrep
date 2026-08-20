import { JobCard } from "@/components/jobs/JobCard";
import type { MatchedJobPosting } from "@/types/job";

interface JobListProps {
  postings: MatchedJobPosting[];
  isSelected: (id: string) => boolean;
  onToggle: (id: string) => void;
  // See JobCard's `disabled` -- true once the selection cap is reached.
  isMaxed?: boolean;
}

export function JobList({
  postings,
  isSelected,
  onToggle,
  isMaxed = false,
}: JobListProps) {
  if (postings.length === 0) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No postings matched your target position this time — try a
        broader title, or check back later as more get ingested.
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
