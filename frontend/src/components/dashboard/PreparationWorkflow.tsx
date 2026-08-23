import Link from "next/link";

interface PreparationWorkflowProps {
  roadmapCount: number;
}

interface WorkflowStep {
  step: number;
  label: string;
  detail: string;
  cta: string;
  href: string;
}

// The stops in the JobPrep workflow (see AGENTS.md / product context:
// resume -> jobs -> roadmap). Numbered because this genuinely is a
// sequence, not decoration. No completed/current state is shown for
// Resume or Jobs -- the backend doesn't expose anything the dashboard
// could check that against (no GET for persisted skills, no history for
// job selections). Roadmaps is the one step with a real number behind it
// (roadmapCount, from the same GET /roadmaps call ActiveRoadmap uses), so
// it's the only one annotated.
//
// Deliberately no separate "Skill gap" step -- it lives on the same /jobs
// page as "Find jobs" (postings are shown together with their required
// skills there), so a dedicated step just duplicated the destination
// without adding a real distinction.
function buildSteps(roadmapCount: number): WorkflowStep[] {
  return [
    {
      step: 1,
      label: "Resume",
      detail: "Review the skills extracted from your resume.",
      cta: "Update resume",
      href: "/resume",
    },
    {
      step: 2,
      label: "Find jobs",
      detail: "Discover live postings, select roles, and compare required skills against yours.",
      cta: "Explore jobs",
      href: "/jobs",
    },
    {
      step: 3,
      label: "Roadmaps",
      detail: roadmapCount > 0
        ? `Revisit your ${roadmapCount} saved roadmap${roadmapCount === 1 ? "" : "s"}.`
        : "Create your first preparation roadmap.",
      cta: "View roadmaps",
      href: "/roadmaps",
    },
  ];
}

export function PreparationWorkflow({ roadmapCount }: PreparationWorkflowProps) {
  const steps = buildSteps(roadmapCount);

  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-slate">
        Your preparation
      </p>
      <div className="mt-3 grid gap-6 sm:grid-cols-3">
        {steps.map((step) => (
          <Link
            key={step.label}
            href={step.href}
            className="group block border-t border-line pt-3 sm:border-t-0 sm:pt-0"
          >
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-xs text-blaze">
                {String(step.step).padStart(2, "0")}
              </span>
              <span className="font-display text-sm font-semibold text-ink group-hover:text-brand">
                {step.label}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-slate">{step.detail}</p>
            <p className="mt-1.5 text-sm font-medium text-brand underline decoration-blaze underline-offset-4">
              {step.cta} →
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
