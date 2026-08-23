import { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
}

// primary = blaze-orange "go" action, reserved for the one main action per
// screen (Get started, Find matching jobs, Create roadmap). secondary =
// outlined ink, the default/neutral action. ghost = text-only, for
// low-emphasis actions like Clear/Cancel that shouldn't compete with either.
export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium tracking-tight transition-colors disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-paper";
  const styles =
    variant === "primary"
      ? "bg-blaze text-white hover:bg-blaze-strong focus-visible:ring-blaze"
      : variant === "secondary"
        ? "border border-line text-ink hover:border-ink hover:bg-surface focus-visible:ring-ink"
        : "text-slate hover:text-ink underline underline-offset-4 decoration-line hover:decoration-ink focus-visible:ring-slate";

  return <button className={`${base} ${styles} ${className}`} {...props} />;
}
