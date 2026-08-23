import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useRoadmapProgress } from "@/hooks/useRoadmapProgress";
import type { RoadmapResponse } from "@/types/roadmap";

interface ActiveRoadmapProps {
  roadmap: RoadmapResponse | null;
  loading: boolean;
}

// The Dashboard's primary section: the most recently created roadmap
// (GET /roadmaps is already ordered newest-first server-side -- there's
// no separate "active" flag on Roadmap, so "most recent" is the most
// defensible stand-in). Progress here is real and persisted -- it reads
// the exact same completed_action_items useRoadmapProgress reads on
// /roadmaps, so checking a box there updates what shows up here the next
// time this loads. This card itself is read-only (no checkboxes) -- the
// interactive checklist lives on /roadmaps via RoadmapViewer.
export function ActiveRoadmap({ roadmap, loading }: ActiveRoadmapProps) {
  if (loading) {
    return <p className="text-sm text-slate">Loading your roadmap...</p>;
  }

  if (!roadmap) {
    return (
      <Card className="text-center">
        <p className="text-sm text-slate">
          No roadmap yet — every route starts with a first step.{" "}
          <Link href="/jobs" className="text-ink underline decoration-blaze underline-offset-2">
            Find matching jobs
          </Link>
          , select a few, and create one.
        </p>
      </Card>
    );
  }

  return <ActiveRoadmapCard roadmap={roadmap} />;
}

function ActiveRoadmapCard({ roadmap }: { roadmap: RoadmapResponse }) {
  const steps = [...roadmap.steps].sort((a, b) => a.order - b.order);
  const progress = useRoadmapProgress(roadmap);

  // The first step that isn't fully checked off yet -- falls back to the
  // last step once everything's done. Real, since it's derived from
  // persisted completed_action_items, not a guess at "current phase."
  const nextStep =
    steps.find(
      (step) =>
        step.action_items.length > 0 &&
        progress.completedCountForStep(step.order) < step.action_items.length,
    ) ?? steps[steps.length - 1];

  const percent =
    progress.totalCount > 0
      ? Math.round((progress.completedCount / progress.totalCount) * 100)
      : null;

  return (
    <Card className="space-y-5">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
          Your roadmap
        </p>
        <h2 className="mt-1 font-display text-xl font-bold tracking-tight text-brand sm:text-2xl">
          {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
        </h2>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate">
          <span>For {roadmap.target_position}</span>
          {roadmap.overview.estimated_duration && (
            <Badge>{roadmap.overview.estimated_duration}</Badge>
          )}
          {steps.length > 0 && (
            <span>
              {steps.length} phase{steps.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>

      {percent !== null && (
        <div>
          <div className="flex items-baseline justify-between text-xs text-slate">
            <span>
              {progress.completedCount} of {progress.totalCount} action items
              completed
            </span>
            <span className="font-mono">{percent}%</span>
          </div>
          <div className="mt-1.5 h-2 rounded-full bg-ink/8">
            <div
              className="h-full rounded-full bg-brand transition-[width]"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      )}

      {nextStep && (
        <div className="border-t border-line pt-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.15em] text-slate">
            Next — Phase {nextStep.order}
          </p>
          <p className="mt-1 font-display text-base font-semibold text-ink">
            {nextStep.title}
          </p>
          {nextStep.why_it_matters && (
            <p className="mt-1 line-clamp-2 text-sm text-slate">
              {nextStep.why_it_matters}
            </p>
          )}
          {nextStep.action_items.length > 0 && (
            <p className="mt-1 text-xs text-slate">
              {progress.completedCountForStep(nextStep.order)} of{" "}
              {nextStep.action_items.length} action items done
            </p>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Link href="/roadmaps">
          <Button>Continue roadmap →</Button>
        </Link>
      </div>
    </Card>
  );
}
