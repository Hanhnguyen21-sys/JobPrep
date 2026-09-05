"use client";

import { useState } from "react";
import Link from "next/link";
import { JobList } from "@/components/jobs/JobList";
import { MaxSelectionNotice } from "@/components/jobs/MaxSelectionNotice";
import { Pagination } from "@/components/jobs/Pagination";
import { SelectionBar } from "@/components/jobs/SelectionBar";
import { RoadmapCreatedModal } from "@/components/roadmap/RoadmapCreatedModal";
import { RoadmapViewer } from "@/components/roadmap/RoadmapViewer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useJobMatch } from "@/hooks/useJobMatch";
import { useJobSelection } from "@/hooks/useJobSelection";
import { useRoadmapGeneration } from "@/hooks/useRoadmapGeneration";
import { MAX_SELECTED_POSTINGS } from "@/types/job";

export default function JobsPage() {
  const {
    result,
    page,
    loading,
    pageLoading,
    refreshing,
    error,
    needsTargetPosition,
    findMatches,
    goToPage,
  } = useJobMatch();
  const { isSelected, toggle, clear, selectedPostings, selectedCount, isMaxed } =
    useJobSelection();
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
    <div className="theme-brand flex-1 bg-paper text-ink">
      <div className="mx-auto w-full max-w-6xl space-y-8 p-6 sm:p-8">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-brand">
            Matching jobs
          </h1>
          <p className="mt-1 text-sm text-slate">
            Matches postings from the new-grad job board against the position
            you saved on your resume, and compares their required skills
            against yours.
          </p>
        </div>

        <Card className="space-y-4">
          <Button onClick={handleFindMatches} disabled={loading}>
            {loading ? "Searching..." : "Find matching jobs"}
          </Button>

          {needsTargetPosition && (
            <p className="text-sm text-danger">
              You haven&apos;t set a target position yet.{" "}
              <Link href="/resume" className="underline">
                Submit your resume
              </Link>{" "}
              with the position you&apos;re looking for first.
            </p>
          )}

          {error && <p className="text-sm text-danger">{error}</p>}
        </Card>

        {result && (
          <Card className="space-y-4">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="font-mono text-xs uppercase tracking-[0.15em] text-slate">
                {result.total_count} matching posting
                {result.total_count === 1 ? "" : "s"}
              </h2>
              {result.total_count > 0 && (
                <p className="text-xs text-slate">
                  Check up to {MAX_SELECTED_POSTINGS} to build a roadmap from
                </p>
              )}
            </div>
            {refreshing && (
              <p className="text-xs text-slate">
                {result.total_count > 0
                  ? "Showing existing matches while we check for new postings..."
                  : "Looking for matches -- this can take a little while the first time..."}
              </p>
            )}
            {isMaxed && <MaxSelectionNotice />}
            <div className={pageLoading ? "opacity-50 transition-opacity" : ""}>
              <JobList
                postings={result.postings}
                isSelected={isSelected}
                onToggle={toggle}
                isMaxed={isMaxed}
                totalCount={result.total_count}
              />
            </div>
            <Pagination
              page={page}
              totalPages={result.total_pages}
              totalCount={result.total_count}
              pageSize={result.page_size}
              onPrev={() => goToPage(page - 1)}
              onNext={() => goToPage(page + 1)}
              disabled={loading || pageLoading}
            />
          </Card>
        )}

        {roadmapError && (
          <Card className="space-y-1 border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{roadmapError}</p>
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
    </div>
  );
}
