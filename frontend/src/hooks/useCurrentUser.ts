"use client";

import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/api/users";
import type { CurrentUser } from "@/types/user";

// Fetches the current user's own-backend profile (full_name in
// particular -- Supabase's auth user, from useAuth, only reliably has
// email) on mount. Same fetch-on-mount shape as useRoadmaps.
export function useCurrentUser() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    getCurrentUser()
      .then((response) => {
        if (!cancelled) setUser(response);
      })
      .catch(() => {
        // Non-critical for the dashboard greeting -- falls back to email.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { user, loading };
}
