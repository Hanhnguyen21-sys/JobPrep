"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { signOut } from "@/lib/auth";
import { Button } from "@/components/ui/Button";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/resume", label: "Resume" },
  { href: "/jobs", label: "Jobs" },
  { href: "/roadmaps", label: "Roadmaps" },
];

export function Navbar() {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  async function handleLogout() {
    await signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <nav className="flex items-center justify-between border-b border-line px-6 py-4">
      <Link
        href="/"
        className="flex items-center gap-2 font-display text-base font-semibold tracking-tight text-ink"
      >
        <span aria-hidden className="h-2 w-2 rounded-full bg-blaze" />
        JobPrep
      </Link>

      <div className="flex items-center gap-6 text-sm">
        {!loading && isAuthenticated ? (
          <>
            <div className="hidden items-center gap-5 sm:flex">
              {NAV_LINKS.map((link) => {
                const active = pathname?.startsWith(link.href);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`underline-offset-4 transition-colors ${
                      active
                        ? "font-medium text-ink underline decoration-blaze decoration-2"
                        : "text-slate hover:text-ink"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </div>
            <Button variant="secondary" onClick={handleLogout}>
              Log out
            </Button>
          </>
        ) : !loading ? (
          <>
            <Link href="/login" className="text-slate hover:text-ink">
              Log in
            </Link>
            <Link href="/signup">
              <Button>Sign up</Button>
            </Link>
          </>
        ) : null}
      </div>
    </nav>
  );
}
