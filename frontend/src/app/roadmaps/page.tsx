"use client";

import { useState } from "react";
import Link from "next/link";
import { RoadmapViewer } from "@/components/roadmap/RoadmapViewer";
import { Card } from "@/components/ui/Card";
import { useRoadmaps } from "@/hooks/useRoadmaps";

export default function RoadmapsPage() {
  const { roadmaps, loading, error, deletingId, deleteError, removeRoadmap } =
    useRoadmaps();
  // Which roadmap (if any) is showing its inline "delete this?" confirm --
  // deliberately not a native confirm() dialog, to match the rest of the
  // app's in-page confirmation style (e.g. RoadmapCreatedModal). Only one
  // card confirms at a time.
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  async function handleConfirmDelete(roadmapId: string) {
    await removeRoadmap(roadmapId);
    setConfirmingId(null);
  }

  return (
    <div className="theme-brand flex-1 bg-paper text-ink">
      <div className="w-full space-y-8 p-6 sm:p-8 lg:px-16">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-brand">
            Your roadmaps
          </h1>
          <p className="mt-1 text-sm text-slate">
            Every roadmap you&apos;ve generated from{" "}
            <Link href="/jobs" className="underline decoration-blaze underline-offset-2">
              selected job postings
            </Link>
            , newest first.
          </p>
        </div>

        {loading && <p className="text-sm text-slate">Loading...</p>}

        {error && (
          <Card className="border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{error}</p>
          </Card>
        )}

        {deleteError && (
          <Card className="border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{deleteError}</p>
          </Card>
        )}

        {!loading && !error && roadmaps.length === 0 && (
          <Card className="text-center">
            <p className="text-sm text-slate">
              No roadmaps yet — every route starts with a first step.{" "}
              <Link href="/jobs" className="text-ink underline decoration-blaze underline-offset-2">
                Find matching jobs
              </Link>
              , select a few, and create one.
            </p>
          </Card>
        )}

        <div className="space-y-6">
          {roadmaps.map((roadmap) => (
            <div key={roadmap.id} className="relative">
              <RoadmapViewer roadmap={roadmap} />
              <div className="absolute right-4 top-4 flex items-center gap-2">
                {confirmingId === roadmap.id ? (
                  <>
                    <span className="text-xs text-slate">
                      Delete this roadmap?
                    </span>
                    <button
                      type="button"
                      onClick={() => handleConfirmDelete(roadmap.id)}
                      disabled={deletingId === roadmap.id}
                      className="text-xs font-medium text-danger underline disabled:opacity-50"
                    >
                      {deletingId === roadmap.id ? "Deleting..." : "Confirm"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(null)}
                      disabled={deletingId === roadmap.id}
                      className="text-xs text-slate underline hover:text-ink disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmingId(roadmap.id)}
                    className="text-xs text-slate underline hover:text-danger"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
