import { HTMLAttributes } from "react";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "technical" | "soft" | "have" | "missing";
}

// Skill tags read as field-guide labels: mono type, pill shape. `have` /
// `missing` are the semantically loaded ones — a skill you already have is
// a solid, reached waypoint; a skill you're missing is an open, dashed one
// still ahead on the route (see SkillGapList).
export function Badge({
  variant = "default",
  className = "",
  ...props
}: BadgeProps) {
  const base =
    "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-tight";
  const styles =
    variant === "technical"
      ? "border-line bg-surface text-ink"
      : variant === "soft"
        ? "border-transparent bg-pine-tint text-pine"
        : variant === "have"
          ? "border-transparent bg-pine text-white"
          : variant === "missing"
            ? "border-dashed border-slate/50 bg-transparent text-slate"
            : "border-line bg-transparent text-slate";

  return <span className={`${base} ${styles} ${className}`} {...props} />;
}
