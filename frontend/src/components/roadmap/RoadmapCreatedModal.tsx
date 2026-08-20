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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-6 shadow-lg dark:bg-zinc-950"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-green-600 dark:text-green-400">
          Roadmap created
        </p>
        <h2 className="mt-1 text-lg font-semibold">
          {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
        </h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {roadmap.overview.headline}
        </p>
        <p className="mt-2 text-xs text-zinc-500">
          {roadmap.steps.length} step{roadmap.steps.length === 1 ? "" : "s"}{" "}
          — saved to your{" "}
          <Link href="/roadmaps" className="underline">
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
