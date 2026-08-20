import { HTMLAttributes } from "react";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "technical" | "soft";
}

export function Badge({
  variant = "default",
  className = "",
  ...props
}: BadgeProps) {
  const base =
    "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";
  const styles =
    variant === "technical"
      ? "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
      : variant === "soft"
        ? "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300"
        : "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300";

  return <span className={`${base} ${styles} ${className}`} {...props} />;
}
