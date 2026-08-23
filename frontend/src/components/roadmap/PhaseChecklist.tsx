"use client";

interface PhaseChecklistProps {
  items: string[];
  isDone: (index: number) => boolean;
  onToggle: (index: number) => void;
}

// Interactive checklist for a phase's action items. Controlled by the
// caller (RoadmapPhaseColumn, via RoadmapViewer's useRoadmapProgress) so
// the checked state is the same persisted data the Dashboard's
// ActiveRoadmap summary reads -- this component owns no state of its own.
export function PhaseChecklist({ items, isDone, onToggle }: PhaseChecklistProps) {
  if (items.length === 0) return null;

  return (
    <ul className="space-y-2">
      {items.map((item, index) => {
        const checked = isDone(index);
        const id = `checkpoint-${index}-${item.slice(0, 12)}`;
        return (
          <li key={index}>
            <label
              htmlFor={id}
              className="flex cursor-pointer items-start gap-2.5 rounded-md py-1 text-xs"
            >
              <input
                id={id}
                type="checkbox"
                checked={checked}
                onChange={() => onToggle(index)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-line accent-pine focus-visible:ring-2 focus-visible:ring-pine"
              />
              <span
                className={
                  checked ? "text-slate line-through decoration-slate/60" : "text-ink"
                }
              >
                {item}
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}
