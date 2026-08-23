import { Suspense } from "react";
import Link from "next/link";
import { LoginForm } from "@/components/auth/LoginForm";
import { Card } from "@/components/ui/Card";

export default function LoginPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
          Welcome back
        </p>
        <h1 className="mt-1 mb-6 font-display text-2xl font-semibold tracking-tight text-ink">
          Log in
        </h1>
        <Suspense>
          <LoginForm />
        </Suspense>
        <p className="mt-4 text-sm text-slate">
          No account?{" "}
          <Link href="/signup" className="font-medium text-ink underline decoration-blaze underline-offset-4">
            Sign up
          </Link>
        </p>
      </Card>
    </div>
  );
}
