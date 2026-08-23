import { apiFetch } from "@/lib/api/client";
import type { CurrentUser } from "@/types/user";

// Calls GET /users/me -- the current user's own profile row (full_name,
// email, created_at). Separate module from lib/auth.ts's Supabase
// session/user, same split as elsewhere in lib/api/*: this is our own
// backend's view of the user, not Supabase's.
export async function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/users/me");
}
