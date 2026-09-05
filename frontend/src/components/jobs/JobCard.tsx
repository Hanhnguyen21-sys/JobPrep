"use client";

import { useEffect, useRef, useState } from "react";
import { Card } from "@/components/ui/Card";
import { MAX_NOTICE_ID } from "@/components/jobs/MaxSelectionNotice";
import type { MatchedJobPosting } from "@/types/job";

interface JobCardProps {
  posting: MatchedJobPosting;
  selected: boolean;
  // Passes the whole posting (not just its id) so selection state can
  // hold onto it across page changes -- see hooks/useJobSelection.ts.
  onToggle: (posting: MatchedJobPosting) => void;
  // True when the MAX_SELECTED_POSTINGS cap is reached and this posting
  // isn't one of the selected ones -- the checkbox goes inert (see
  // hooks/useJobSelection.ts) and is wired to the MaxSelectionNotice for
  // assistive tech.
  disabled?: boolean;
}

export function JobCard({
  posting,
  selected,
  onToggle,
  disabled = false,
}: JobCardProps) {
  // Brief highlight when the user clicks a capped-out card, so there's
  // feedback at the point of interaction and not only in the banner
  // elsewhere on the page. A disabled <input> swallows its own click, but
  // the click on the surrounding card row still bubbles here.
  const [nudge, setNudge] = useState(false);
  const nudgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (nudgeTimer.current) clearTimeout(nudgeTimer.current);
    };
  }, []);

  function handleCardClick() {
    if (!disabled) return;
    setNudge(true);
    if (nudgeTimer.current) clearTimeout(nudgeTimer.current);
    nudgeTimer.current = setTimeout(() => setNudge(false), 600);
  }

  return (
    <Card
      onClick={handleCardClick}
      className={`flex items-start gap-3 transition-colors ${
        selected ? "border-blaze" : ""
      } ${disabled ? "opacity-50" : ""} ${
        nudge ? "border-blaze ring-2 ring-blaze/50" : ""
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(posting)}
        disabled={disabled}
        aria-disabled={disabled || undefined}
        aria-describedby={disabled ? MAX_NOTICE_ID : undefined}
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
