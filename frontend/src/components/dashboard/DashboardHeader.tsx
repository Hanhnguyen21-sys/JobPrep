interface DashboardHeaderProps {
  name: string;
  targetPosition: string | null;
}

// Compact intro, not a hero -- one eyebrow, one greeting, one line of
// context. targetPosition comes from the user's most recent roadmap
// (see app/dashboard/page.tsx) since UserRead doesn't expose
// User.target_position today -- omitted rather than guessed when there
// isn't one yet.
export function DashboardHeader({ name, targetPosition }: DashboardHeaderProps) {
  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
        Dashboard
      </p>
      <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight text-brand">
        Welcome back, {name}.
      </h1>
      {targetPosition && (
        <p className="mt-1 text-sm text-slate">
          Preparing for <span className="text-ink">{targetPosition}</span>
        </p>
      )}
    </div>
  );
}
