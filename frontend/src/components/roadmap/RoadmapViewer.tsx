import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { Resource, RoadmapResponse } from "@/types/roadmap";

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

function ResourceLink({ resource }: { resource: Resource }) {
  const label = [RESOURCE_TYPE_LABEL[resource.type], resource.provider]
    .filter(Boolean)
    .join(" · ");

  const content = (
    <>
      <span className="font-medium">{resource.title}</span>
      {label && <span className="text-zinc-500"> ({label})</span>}
    </>
  );

  return (
    <li className="text-sm text-zinc-600 dark:text-zinc-400">
      {resource.url ? (
        <a
          href={resource.url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-dotted underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-200"
        >
          {content}
        </a>
      ) : (
        content
      )}
    </li>
  );
}

// Renders a generated roadmap: a short overview (headline, priority
// skills, estimated duration), which postings it was built from, and a
// vertical timeline of steps -- each with the skills it targets, why it
// matters, a concrete checklist, suggested resources, an optional project,
// duration, and how to know it's done. No dedicated RoadmapCard.tsx yet
// (that's for a future roadmaps list page, per the file-structure plan) --
// this is the single full view used inline on /jobs right after
// generation and reused as-is on /roadmaps.
//
// Deliberately a linear timeline, not a node/branch graph -- steps are a
// flat ordered sequence with no dependencies between them, so a graph
// library would be complexity this data doesn't need. See
// claude/roadmap-restructure-plan.md in the project for the reasoning.
export function RoadmapViewer({ roadmap }: RoadmapViewerProps) {
  const steps = [...roadmap.steps].sort((a, b) => a.order - b.order);
  const { overview } = roadmap;

  return (
    <Card className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">
          {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
        </h2>
        {roadmap.title && (
          <p className="text-xs text-zinc-500">For {roadmap.target_position}</p>
        )}

        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {overview.headline}
        </p>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          {overview.estimated_duration && (
            <Badge>{overview.estimated_duration}</Badge>
          )}
          {overview.priority_skills.map((skill) => (
            <Badge key={skill} variant="technical">
              {skill}
            </Badge>
          ))}
        </div>

        <p className="mt-3 text-xs text-zinc-500">
          Built from {roadmap.source_postings.length} posting
          {roadmap.source_postings.length === 1 ? "" : "s"}:{" "}
          {roadmap.source_postings
            .map((p) => `${p.title} @ ${p.company_name}`)
            .join(", ")}
        </p>
      </div>

      <ol className="space-y-6">
        {steps.map((step) => (
          <li
            key={step.order}
            className="border-l-2 border-zinc-200 pl-4 dark:border-zinc-800"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs font-semibold text-zinc-500">
                Step {step.order}
              </span>
              <h3 className="font-medium">{step.title}</h3>
              {step.duration && (
                <span className="text-xs text-zinc-500">
                  · {step.duration}
                </span>
              )}
            </div>

            {step.skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {step.skills.map((skill) => (
                  <Badge
                    key={skill}
                    variant="technical"
                    className={
                      skill === step.focus_skill
                        ? "ring-1 ring-blue-400 dark:ring-blue-600"
                        : undefined
                    }
                  >
                    {skill}
                  </Badge>
                ))}
              </div>
            )}

            {step.why_it_matters && (
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {step.why_it_matters}
              </p>
            )}

            {step.action_items.length > 0 && (
              <ul className="mt-2 space-y-1">
                {step.action_items.map((item, index) => (
                  <li
                    key={index}
                    className="flex gap-2 text-sm text-zinc-700 dark:text-zinc-300"
                  >
                    <span aria-hidden className="text-zinc-400">
                      ☐
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )}

            {step.project && (
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">
                  Project:
                </span>{" "}
                {step.project}
              </p>
            )}

            {step.resources.length > 0 && (
              <ul className="mt-2 space-y-1">
                {step.resources.map((resource, index) => (
                  <ResourceLink key={index} resource={resource} />
                ))}
              </ul>
            )}

            {step.success_criteria.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Done when
                </p>
                <ul className="mt-1 space-y-1">
                  {step.success_criteria.map((criterion, index) => (
                    <li
                      key={index}
                      className="text-sm text-zinc-600 dark:text-zinc-400"
                    >
                      {criterion}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}
