import { PhaseChecklist } from "@/components/roadmap/PhaseChecklist";
import type { RoadmapStep } from "@/types/roadmap";

interface RoadmapPhaseColumnProps {
  step: RoadmapStep;
  isFirst: boolean;
  isLast: boolean;
  isItemDone: (itemIndex: number) => boolean;
  onToggleItem: (itemIndex: number) => void;
}

// One column in the horizontal phase timeline: a "Phase N" waypoint on
// the shared connecting line, the phase's goal, its checklist, and any
// project/success-criteria footnotes. Deliberately self-contained (the
// node + its left/right line halves live inside this same column) so
// placing N of these in a row produces one continuous line across
// columns without any parent-level pixel math -- each column's line
// halves line up because every column is the same fixed width.
export function RoadmapPhaseColumn({
  step,
  isFirst,
  isLast,
  isItemDone,
  onToggleItem,
}: RoadmapPhaseColumnProps) {
  return (
    <div className="flex w-64 shrink-0 flex-col items-center px-4 text-center">
      <p className="font-mono text-xs font-semibold uppercase tracking-[0.15em] text-blaze">
        Phase {step.order}
      </p>

      <div className="mt-3 flex w-full items-center">
        <span className={`h-0.5 flex-1 ${isFirst ? "bg-transparent" : "bg-blaze"}`} />
        <span
          aria-hidden
          className="h-4 w-4 shrink-0 rounded-full border-2 border-blaze bg-paper"
        />
        <span className={`h-0.5 flex-1 ${isLast ? "bg-transparent" : "bg-blaze"}`} />
      </div>

      <span aria-hidden className="mt-2 h-5 w-px bg-line" />

      <h3 className="line-clamp-2 font-display text-sm font-semibold tracking-tight text-ink">
        {step.title}
      </h3>
      {step.duration && (
        <p className="mt-1 font-mono text-[11px] text-slate">{step.duration}</p>
      )}
      {step.why_it_matters && (
        <p className="mt-2 line-clamp-3 text-xs text-slate">{step.why_it_matters}</p>
      )}

      {step.action_items.length > 0 && (
        <>
          <span aria-hidden className="mt-3 h-5 w-px bg-line" />
          <div className="w-full text-left">
            <PhaseChecklist
              items={step.action_items}
              isDone={isItemDone}
              onToggle={onToggleItem}
            />
          </div>
        </>
      )}

      {(step.project || step.success_criteria.length > 0) && (
        <div className="mt-3 w-full space-y-1.5 border-t border-line pt-3 text-left">
          {step.project && (
            <p className="text-xs text-slate">
              <span className="font-medium text-ink">Project:</span> {step.project}
            </p>
          )}
          {step.success_criteria.length > 0 && (
            <p className="text-xs text-slate">
              <span className="font-medium text-pine">Done when:</span>{" "}
              {step.success_criteria.join(" · ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
