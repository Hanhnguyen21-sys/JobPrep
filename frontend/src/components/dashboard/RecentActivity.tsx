import Link from "next/link";
import type { RoadmapResponse } from "@/types/roadmap";

interface RecentActivityProps {
  roadmaps: RoadmapResponse[];
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

// Secondary section, restrained on purpose -- lists roadmaps beyond the
// one already featured in ActiveRoadmap (app/dashboard/page.tsx passes
// roadmaps.slice(1)). This is the only real "recent activity" the backend
// exposes: job selections aren't persisted (useJobSelection is in-memory
// only) and there's no updated_at on the user profile to show a resume
// change. Renders nothing with fewer than 1 item to show, rather than a
// placeholder -- callers should only mount this when there's something
// real to list.
export function RecentActivity({ roadmaps }: RecentActivityProps) {
  if (roadmaps.length === 0) return null;

  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-slate">
        Recent activity
      </p>
      <ul className="mt-3 divide-y divide-line">
        {roadmaps.map((roadmap) => (
          <li key={roadmap.id}>
            <Link
              href="/roadmaps"
              className="flex items-baseline justify-between gap-3 py-2 text-sm hover:text-brand"
            >
              <span className="truncate text-ink">
                {roadmap.title ?? `Roadmap for ${roadmap.target_position}`}
              </span>
              <span className="shrink-0 font-mono text-xs text-slate">
                {formatDate(roadmap.created_at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
