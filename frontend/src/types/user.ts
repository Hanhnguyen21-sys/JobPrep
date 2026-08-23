// Mirrors backend/app/schemas/user.py's UserRead -- keep these two in sync
// by hand, same convention as types/job.ts / types/skill.ts / types/roadmap.ts.

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
}
