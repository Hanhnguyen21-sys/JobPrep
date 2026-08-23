import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { RoadmapPhaseColumn } from "@/components/roadmap/RoadmapPhaseColumn";
import { useRoadmapProgress } from "@/hooks/useRoadmapProgress";
import type { Resource, RoadmapResponse, RoadmapStep } from "@/types/roadmap";

interface RoadmapViewerProps {
  roadmap: RoadmapResponse;
}

const RESOURCE_TYPE_LABEL: Record<Resource["type"], string> = {
  course: "Course",
  article: "Article",
  project: "Project",
  certification: "Certification",
  tool: "Tool",
};

interface PickedResource {
  resource: Resource;
  stepOrder: number;
}

// One shared "Recommended resources" section for the whole roadmap
// (rather than one per phase) -- flattens every step's resources,
// prefers one course/tutorial-shaped pick and one article/doc-shaped
// pick (the closest we have to "book or documentation"), then fills any
// remaining slot in step order. Never invents a resource -- an empty
// result renders an empty state instead.
function pickRoadmapResources(steps: RoadmapStep[]): PickedResource[] {
  const flat: PickedResource[] = steps.flatMap((step) =>
    step.resources.map((resource) => ({ resource, stepOrder: step.order })),
  );
  const course = flat.find((f) => f.resource.type === "course");
  const article = flat.find((f) => f.resource.type === "article" && f !== course);
  const preferred = [course, article].filter((f): f is PickedResource => Boolean(f));
  const rest = flat.filter((f) => !preferred.includes(f));
  return [...preferred, ...rest].slice(0, 2);
}

function ResourceCard({ resource, stepOrder }: PickedResource) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-line bg-paper p-4">
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <Badge>{RESOURCE_TYPE_LABEL[resource.type]}</Badge>
          <span className="font-mono text-[11px] text-slate">Phase {stepOrder}</span>
        </div>
        <p title={resource.title} className="truncate text-sm font-medium text-ink">
          {resource.title}
        </p>
        {resource.provider && <p className="text-xs text-slate">{resource.provider}</p>}
      </div>
      {resource.url && (
        <a
          href={resource.url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-sm font-medium text-ink underline decoration-blaze underline-offset-4 hover:text-blaze"
        >
          View →
        </a>
      )}
    </div>
  );
}

// Renders a generated roadmap: a short overview (headline, estimated
// duration, source postings), a horizontal timeline of phases -- a
// waypoint node per phase on one continuous connecting line
// (RoadmapPhaseColumn), each with its goal and an interactive checklist
// built from action_items -- and one combined "Recommended resources"
// section below it. No dedicated RoadmapCard.tsx yet (that's for a
// future roadmaps list page, per the file-structure plan) -- this is the
// single full view used inline on /jobs right after generation and
// reused as-is on /roadmaps.
export function RoadmapViewer({ roadmap }: RoadmapViewerProps) {
  const steps = [...roadmap.steps].sort((a, b) => a.order - b.order);
  const { overview } = roadmap;
  const resources = pickRoadmapResources(steps);
  const progress = useRoadmapProgress(roadmap);

  return (
    <Card className="space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight text-brand sm:text-3xl">
          {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
        </h2>
        {roadmap.title && (
          <p className="font-mono text-xs text-slate">
            For {roadmap.target_position}
          </p>
        )}

        <p className="mt-2 text-sm text-slate">{overview.headline}</p>

        {overview.estimated_duration && (
          <div className="mt-3">
            <Badge>{overview.estimated_duration}</Badge>
          </div>
        )}

        <p className="mt-3 text-xs text-slate">
          Built from {roadmap.source_postings.length} posting
          {roadmap.source_postings.length === 1 ? "" : "s"}:{" "}
          {roadmap.source_postings
            .map((p) => `${p.title} @ ${p.company_name}`)
            .join(", ")}
        </p>
      </div>

      <div className="-mx-6 overflow-x-auto px-6">
        <div className="flex w-max">
          {steps.map((step, index) => (
            <RoadmapPhaseColumn
              key={step.order}
              step={step}
              isFirst={index === 0}
              isLast={index === steps.length - 1}
              isItemDone={(itemIndex) => progress.isDone(step.order, itemIndex)}
              onToggleItem={(itemIndex) => progress.toggle(step.order, itemIndex)}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-line pt-6">
        <p className="font-mono text-xs uppercase tracking-[0.15em] text-slate">
          Recommended resources
        </p>
        {resources.length > 0 ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {resources.map((picked, index) => (
              <ResourceCard key={index} {...picked} />
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate">
            No resources suggested for this roadmap yet.
          </p>
        )}
      </div>
    </Card>
  );
}
