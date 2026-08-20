"use client";

import { useAuth } from "@/hooks/useAuth";

export default function DashboardPage() {
  const { user, loading } = useAuth();

  if (loading) return <p className="p-6">Loading...</p>;

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">
        Signed in as {user?.email}. Resume upload, job matching, and roadmaps
        land here in later steps.
      </p>
    </div>
  );
}
