import { Card } from "@/components/ui/Card";
import type { MatchedJobPosting } from "@/types/job";

interface JobCardProps {
  posting: MatchedJobPosting;
  selected: boolean;
  onToggle: (id: string) => void;
  // True when the MAX_SELECTED_POSTINGS cap is reached and this posting
  // isn't one of the selected ones -- disables the checkbox instead of
  // letting the user click it and see nothing happen (see
  // hooks/useJobSelection.ts).
  disabled?: boolean;
}

export function JobCard({
  posting,
  selected,
  onToggle,
  disabled = false,
}: JobCardProps) {
  return (
    <Card className={`flex items-start gap-3 ${disabled ? "opacity-60" : ""}`}>
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(posting.id)}
        disabled={disabled}
        aria-label={`Select ${posting.title} at ${posting.company_name}`}
        className="mt-1 h-4 w-4 shrink-0 rounded border-zinc-300 text-black focus:ring-black disabled:cursor-not-allowed dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
      />
      <div className="flex-1 space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-medium">{posting.title}</h3>
          <span className="shrink-0 text-sm text-zinc-500">
            {posting.company_name}
          </span>
        </div>
        {posting.location && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {posting.location}
          </p>
        )}
        {posting.url && (
          <a
            href={posting.url}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm text-blue-600 underline dark:text-blue-400"
          >
            View posting →
          </a>
        )}
      </div>
    </Card>
  );
}
