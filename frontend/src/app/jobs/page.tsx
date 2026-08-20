"use client";

import { useState } from "react";
import Link from "next/link";
import { JobList } from "@/components/jobs/JobList";
import { SelectionBar } from "@/components/jobs/SelectionBar";
import { RoadmapCreatedModal } from "@/components/roadmap/RoadmapCreatedModal";
import { RoadmapViewer } from "@/components/roadmap/RoadmapViewer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useJobMatch } from "@/hooks/useJobMatch";
import { useJobSelection } from "@/hooks/useJobSelection";
import { useRoadmapGeneration } from "@/hooks/useRoadmapGeneration";

export default function JobsPage() {
  const { result, loading, error, needsTargetPosition, findMatches } =
    useJobMatch();
  const { isSelected, toggle, clear, selectedPostings, selectedCount, isMaxed } =
    useJobSelection(result?.postings ?? []);
  const {
    roadmap,
    loading: generatingRoadmap,
    error: roadmapError,
    generate: generateRoadmap,
    clear: clearRoadmap,
  } = useRoadmapGeneration();
  // Separate from `roadmap` itself so the modal doesn't reopen on
  // unrelated re-renders once the user's dismissed it -- roadmap stays
  // populated (RoadmapViewer keeps showing it below) but the modal only
  // shows right after a fresh POST /roadmaps success.
  const [showCreatedModal, setShowCreatedModal] = useState(false);

  async function handleFindMatches() {
    clearRoadmap();
    setShowCreatedModal(false);
    const response = await findMatches();
    // A fresh search means a new set of posting ids -- drop any stale
    // selection from the previous result rather than let checkmarks point
    // at postings that are no longer on screen.
    if (response) clear();
  }

  async function handleCreateRoadmap() {
    const created = await generateRoadmap(
      selectedPostings.map((posting) => posting.id),
    );
    if (created) setShowCreatedModal(true);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      <div>
        <h1 className="text-xl font-semibold">Matching jobs</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Pulls live postings from Greenhouse and Lever, filtered to the
          position you saved on your resume, and compares their required skills
          against yours. This can take longer than a normal page load.
        </p>
      </div>

      <Card className="space-y-4">
        <Button onClick={handleFindMatches} disabled={loading}>
          {loading ? "Searching..." : "Find matching jobs"}
        </Button>

        {needsTargetPosition && (
          <p className="text-sm text-red-600 dark:text-red-400">
            You haven&apos;t set a target position yet.{" "}
            <Link href="/resume" className="underline">
              Submit your resume
            </Link>{" "}
            with the position you&apos;re looking for first.
          </p>
        )}

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
      </Card>

      {result && (
        <Card className="space-y-4">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
              {result.postings.length} matching posting
              {result.postings.length === 1 ? "" : "s"}
            </h2>
            {result.postings.length > 0 && (
              <p className="text-xs text-zinc-500">
                Check up to 10 to build a roadmap from
              </p>
            )}
          </div>
          <JobList
            postings={result.postings}
            isSelected={isSelected}
            onToggle={toggle}
            isMaxed={isMaxed}
          />
        </Card>
      )}

      {roadmapError && (
        <Card className="space-y-1 border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40">
          <p className="text-sm text-red-800 dark:text-red-300">
            {roadmapError}
          </p>
        </Card>
      )}

      {roadmap && <RoadmapViewer roadmap={roadmap} />}

      <SelectionBar
        selectedCount={selectedCount}
        onClear={clear}
        onCreateRoadmap={handleCreateRoadmap}
        generating={generatingRoadmap}
      />

      {showCreatedModal && roadmap && (
        <RoadmapCreatedModal
          roadmap={roadmap}
          onClose={() => setShowCreatedModal(false)}
        />
      )}
    </div>
  );
}
