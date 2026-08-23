"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import type { RoadmapResponse } from "@/types/roadmap";

interface RoadmapCreatedModalProps {
  roadmap: RoadmapResponse;
  onClose: () => void;
}

// Shown once, right after POST /roadmaps succeeds -- confirms creation
// and gives a quick preview before the user dismisses it. The full
// RoadmapViewer is already rendered on the page underneath (and the
// roadmap is saved permanently either way, visible on /roadmaps), so this
// is purely a "yes, that worked" moment, not the only place to see it.
export function RoadmapCreatedModal({
  roadmap,
  onClose,
}: RoadmapCreatedModalProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="flex items-center gap-1.5 font-mono text-xs font-semibold uppercase tracking-[0.15em] text-pine">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-pine" />
          Roadmap created
        </p>
        <h2 className="mt-2 font-display text-lg font-semibold tracking-tight text-ink">
          {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
        </h2>
        <p className="mt-2 text-sm text-slate">{roadmap.overview.headline}</p>
        <p className="mt-2 text-xs text-slate">
          {roadmap.steps.length} step{roadmap.steps.length === 1 ? "" : "s"}{" "}
          — saved to your{" "}
          <Link href="/roadmaps" className="text-ink underline decoration-blaze underline-offset-2">
            roadmap history
          </Link>
          .
        </p>
        <div className="mt-4 flex justify-end">
          <Button onClick={onClose}>Done</Button>
        </div>
      </div>
    </div>
  );
}
