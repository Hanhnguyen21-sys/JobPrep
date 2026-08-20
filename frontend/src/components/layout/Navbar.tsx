"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { signOut } from "@/lib/auth";
import { Button } from "@/components/ui/Button";

export function Navbar() {
  const { isAuthenticated, user, loading } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <nav className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
      <Link href="/" className="font-semibold">
        JobPrep
      </Link>

      <div className="flex items-center gap-4 text-sm">
        {!loading && isAuthenticated ? (
          <>
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/resume">Resume</Link>
            <Link href="/jobs">Jobs</Link>
            <Link href="/roadmaps">Roadmaps</Link>
            <span className="text-zinc-500">{user?.email}</span>
            <Button variant="secondary" onClick={handleLogout}>
              Log out
            </Button>
          </>
        ) : !loading ? (
          <>
            <Link href="/login">Log in</Link>
            <Link href="/signup">
              <Button>Sign up</Button>
            </Link>
          </>
        ) : null}
      </div>
    </nav>
  );
}
