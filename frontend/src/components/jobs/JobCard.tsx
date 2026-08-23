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
    <Card
      className={`flex items-start gap-3 transition-colors ${
        selected ? "border-blaze" : ""
      } ${disabled ? "opacity-50" : ""}`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(posting.id)}
        disabled={disabled}
        aria-label={`Select ${posting.title} at ${posting.company_name}`}
        className="mt-1 h-4 w-4 shrink-0 rounded border-line text-blaze accent-blaze focus-visible:ring-2 focus-visible:ring-blaze disabled:cursor-not-allowed"
      />
      <div className="flex-1 space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-medium text-ink">{posting.title}</h3>
          <span className="shrink-0 font-mono text-xs text-slate">
            {posting.company_name}
          </span>
        </div>
        {posting.location && (
          <p className="text-sm text-slate">{posting.location}</p>
        )}
        {posting.url && (
          <a
            href={posting.url}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm text-blaze underline decoration-blaze/40 underline-offset-2 hover:decoration-blaze"
          >
            View posting →
          </a>
        )}
      </div>
    </Card>
  );
}
