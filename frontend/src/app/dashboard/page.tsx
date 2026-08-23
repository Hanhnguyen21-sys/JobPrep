"use client";

import { ActiveRoadmap } from "@/components/dashboard/ActiveRoadmap";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { PreparationWorkflow } from "@/components/dashboard/PreparationWorkflow";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useRoadmaps } from "@/hooks/useRoadmaps";

// The user's home and continuation point for the JobPrep workflow (resume
// -> jobs -> roadmap -> phases/tasks). Built around whatever is real
// today: the most recent roadmap (GET /roadmaps, newest first) is the
// primary section, and Recent activity is just the rest of that same
// list -- nothing here is computed or invented client-side. See git
// history / PR description for the data audit this layout is based on.
export default function DashboardPage() {
  const { user: authUser, loading: authLoading } = useAuth();
  const { user: profile } = useCurrentUser();
  const { roadmaps, loading: roadmapsLoading } = useRoadmaps();

  if (authLoading) {
    return (
      <div className="p-6">
        <p className="text-sm text-slate">Loading...</p>
      </div>
    );
  }

  const displayName =
    profile?.full_name || authUser?.email?.split("@")[0] || "there";
  const activeRoadmap = roadmaps[0] ?? null;
  const olderRoadmaps = roadmaps.slice(1, 4);

  return (
    <div className="theme-brand flex-1 bg-paper text-ink">
      <div className="mx-auto w-full max-w-6xl space-y-10 p-6 sm:p-8">
        <DashboardHeader
          name={displayName}
          targetPosition={activeRoadmap?.target_position ?? null}
        />

        <PreparationWorkflow roadmapCount={roadmaps.length} />

        <ActiveRoadmap roadmap={activeRoadmap} loading={roadmapsLoading} />

        <RecentActivity roadmaps={olderRoadmaps} />
      </div>
    </div>
  );
}
