"use client";

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { useTracker } from "@/hooks/useTracker";
import {
  TRACKED_JOB_STATUS_LABELS,
  TRACKED_JOB_STATUSES,
} from "@/types/tracker";
import type { TrackedJobResponse, TrackedJobStatus } from "@/types/tracker";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

interface StatusSelectProps {
  job: TrackedJobResponse;
  disabled: boolean;
  onChange: (status: TrackedJobStatus) => void;
}

function StatusSelect({ job, disabled, onChange }: StatusSelectProps) {
  return (
    <select
      value={job.status}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as TrackedJobStatus)}
      aria-label={`Status for ${job.title} at ${job.company_name}`}
      className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blaze disabled:opacity-50"
    >
      {TRACKED_JOB_STATUSES.map((status) => (
        <option key={status} value={status}>
          {TRACKED_JOB_STATUS_LABELS[status]}
        </option>
      ))}
    </select>
  );
}

interface RemoveControlProps {
  confirming: boolean;
  deleting: boolean;
  onRequestConfirm: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}

function RemoveControl({
  confirming,
  deleting,
  onRequestConfirm,
  onConfirm,
  onCancel,
}: RemoveControlProps) {
  if (!confirming) {
    return (
      <button
        type="button"
        onClick={onRequestConfirm}
        className="text-xs text-slate underline hover:text-danger"
      >
        Remove
      </button>
    );
  }

  return (
    <span className="flex items-center justify-end gap-2 whitespace-nowrap text-xs">
      <span className="text-slate">Remove?</span>
      <button
        type="button"
        onClick={onConfirm}
        disabled={deleting}
        className="font-medium text-danger underline disabled:opacity-50"
      >
        {deleting ? "Removing..." : "Confirm"}
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={deleting}
        className="text-slate underline hover:text-ink disabled:opacity-50"
      >
        Cancel
      </button>
    </span>
  );
}

export default function TrackerPage() {
  const {
    trackedJobs,
    loading,
    error,
    updatingId,
    updateError,
    updateStatus,
    deletingId,
    deleteError,
    removeEntry,
  } = useTracker();

  // Which entry (if any) is showing its inline "remove this?" confirm --
  // in-page, not a native confirm() dialog, same style as
  // app/roadmaps/page.tsx's delete flow. Only one at a time.
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  async function handleConfirmDelete(trackedJobId: string) {
    await removeEntry(trackedJobId);
    setConfirmingId(null);
  }

  return (
    <div className="theme-brand flex-1 bg-paper text-ink">
      <div className="mx-auto w-full max-w-6xl space-y-8 p-6 sm:p-8">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-brand">
            Tracker
          </h1>
          <p className="mt-1 text-sm text-slate">
            Jobs you&apos;ve selected on{" "}
            <Link
              href="/jobs"
              className="underline decoration-blaze underline-offset-2"
            >
              Job Match
            </Link>
            , with the status of your application. Update the status as you
            move through each one.
          </p>
        </div>

        {loading && <p className="text-sm text-slate">Loading...</p>}

        {error && (
          <Card className="border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{error}</p>
          </Card>
        )}

        {updateError && (
          <Card className="border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{updateError}</p>
          </Card>
        )}

        {deleteError && (
          <Card className="border-danger/30 bg-danger-tint">
            <p className="text-sm text-danger">{deleteError}</p>
          </Card>
        )}

        {!loading && !error && trackedJobs.length === 0 && (
          <Card className="text-center">
            <p className="text-sm text-slate">
              Nothing tracked yet — select a posting on{" "}
              <Link
                href="/jobs"
                className="text-ink underline decoration-blaze underline-offset-2"
              >
                Job Match
              </Link>{" "}
              and it&apos;ll show up here as &quot;Saved&quot;.
            </p>
          </Card>
        )}

        {!loading && !error && trackedJobs.length > 0 && (
          <>
            {/* Table layout for sm+ screens. */}
            <Card className="hidden overflow-x-auto p-0 sm:block">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line font-mono text-xs uppercase tracking-[0.1em] text-slate">
                    <th scope="col" className="px-4 py-3 font-medium">
                      Company
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Title
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Link
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Added
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Status
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {trackedJobs.map((job) => (
                    <tr key={job.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3 align-top font-mono text-xs text-slate">
                        {job.company_name}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <div className="font-medium text-ink">{job.title}</div>
                        {!job.is_active && (
                          <div className="mt-0.5 text-xs text-slate">
                            Posting no longer active
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {job.url ? (
                          <a
                            href={job.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blaze underline decoration-blaze/40 underline-offset-2 hover:decoration-blaze"
                          >
                            View →
                          </a>
                        ) : (
                          <span className="text-slate">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top text-slate">
                        {formatDate(job.created_at)}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <StatusSelect
                          job={job}
                          disabled={updatingId === job.id}
                          onChange={(status) => updateStatus(job.id, status)}
                        />
                      </td>
                      <td className="px-4 py-3 align-top text-right">
                        <RemoveControl
                          confirming={confirmingId === job.id}
                          deleting={deletingId === job.id}
                          onRequestConfirm={() => setConfirmingId(job.id)}
                          onConfirm={() => handleConfirmDelete(job.id)}
                          onCancel={() => setConfirmingId(null)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            {/* Card list for narrow screens. */}
            <div className="space-y-3 sm:hidden">
              {trackedJobs.map((job) => (
                <Card key={job.id} className="space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="font-medium text-ink">{job.title}</h3>
                    <span className="shrink-0 font-mono text-xs text-slate">
                      {job.company_name}
                    </span>
                  </div>
                  {!job.is_active && (
                    <p className="text-xs text-slate">Posting no longer active</p>
                  )}
                  {job.url && (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block text-sm text-blaze underline decoration-blaze/40 underline-offset-2 hover:decoration-blaze"
                    >
                      View posting →
                    </a>
                  )}
                  <p className="text-xs text-slate">
                    Added {formatDate(job.created_at)}
                  </p>
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <StatusSelect
                      job={job}
                      disabled={updatingId === job.id}
                      onChange={(status) => updateStatus(job.id, status)}
                    />
                    <RemoveControl
                      confirming={confirmingId === job.id}
                      deleting={deletingId === job.id}
                      onRequestConfirm={() => setConfirmingId(job.id)}
                      onConfirm={() => handleConfirmDelete(job.id)}
                      onCancel={() => setConfirmingId(null)}
                    />
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
