import Link from "next/link";
import { Button } from "@/components/ui/Button";

const ROUTE_STOPS = [
  { label: "Resume", detail: "Extract your skills" },
  { label: "Match", detail: "Find open postings" },
  { label: "Roadmap", detail: "Close the gap" },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-10 p-6 text-center">
      <div className="max-w-lg space-y-4">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
          Plot your route
        </p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
          Land your next job, faster.
        </h1>
        <p className="mx-auto max-w-md text-base text-slate">
          Upload your resume, match against real job postings, and get a
          personalized roadmap to close the gap.
        </p>
      </div>

      <Link href="/signup">
        <Button>Get started</Button>
      </Link>

      {/* Signature waypoint route — the same visual language RoadmapViewer
          uses for its step timeline, previewed here at product scale. */}
      <ol className="mt-4 flex w-full max-w-xl items-start justify-between px-4">
        {ROUTE_STOPS.map((stop, index) => (
          <li key={stop.label} className="relative flex flex-1 flex-col items-center">
            {index < ROUTE_STOPS.length - 1 && (
              <span
                aria-hidden
                className="absolute left-1/2 top-2 h-px w-full bg-line"
                style={{ backgroundImage: "linear-gradient(to right, var(--blaze) 0 60%, transparent 60%)", backgroundSize: "8px 1px" }}
              />
            )}
            <span
              aria-hidden
              className="relative z-10 flex h-4 w-4 items-center justify-center rounded-full border-2 border-blaze bg-paper font-mono text-[10px] text-blaze"
            >
              {index === 0 && <span className="h-1.5 w-1.5 rounded-full bg-blaze" />}
            </span>
            <span className="mt-3 font-display text-sm font-medium text-ink">
              {stop.label}
            </span>
            <span className="mt-0.5 text-xs text-slate">{stop.detail}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
