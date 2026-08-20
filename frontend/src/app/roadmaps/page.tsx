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
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      <div>
        <h1 className="text-xl font-semibold">Your roadmaps</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Every roadmap you&apos;ve generated from{" "}
          <Link href="/jobs" className="underline">
            selected job postings
          </Link>
          , newest first.
        </p>
      </div>

      {loading && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Loading...</p>
      )}

      {error && (
        <Card className="border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </Card>
      )}

      {deleteError && (
        <Card className="border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40">
          <p className="text-sm text-red-800 dark:text-red-300">
            {deleteError}
          </p>
        </Card>
      )}

      {!loading && !error && roadmaps.length === 0 && (
        <Card>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No roadmaps yet.{" "}
            <Link href="/jobs" className="underline">
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
                  <span className="text-xs text-zinc-500">
                    Delete this roadmap?
                  </span>
                  <button
                    type="button"
                    onClick={() => handleConfirmDelete(roadmap.id)}
                    disabled={deletingId === roadmap.id}
                    className="text-xs font-medium text-red-600 underline hover:text-red-700 disabled:opacity-50 dark:text-red-400"
                  >
                    {deletingId === roadmap.id ? "Deleting..." : "Confirm"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingId(null)}
                    disabled={deletingId === roadmap.id}
                    className="text-xs text-zinc-500 underline hover:text-zinc-700 disabled:opacity-50 dark:hover:text-zinc-300"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmingId(roadmap.id)}
                  className="text-xs text-zinc-500 underline hover:text-red-600 dark:hover:text-red-400"
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
