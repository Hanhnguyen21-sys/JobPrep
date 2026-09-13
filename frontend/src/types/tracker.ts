// Mirrors backend/app/schemas/tracked_job.py -- keep these in sync by
// hand, same convention as types/job.ts / types/roadmap.ts.

export type TrackedJobStatus =
  | "saved"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

// Display order for the status <select> on /tracker -- the rough order
// an application actually moves through.
export const TRACKED_JOB_STATUSES: TrackedJobStatus[] = [
  "saved",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

export const TRACKED_JOB_STATUS_LABELS: Record<TrackedJobStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export interface TrackedJobResponse {
  id: string;
  job_posting_id: string;
  company_name: string;
  title: string;
  url: string | null;
  // Live JobPosting.is_active at response time -- a tracked entry stays
  // in the list (and keeps its status) even after ingestion marks the
  // underlying posting inactive; this just flags that in the UI.
  is_active: boolean;
  status: TrackedJobStatus;
  created_at: string;
  updated_at: string;
}
