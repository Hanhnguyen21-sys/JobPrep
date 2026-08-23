import Link from "next/link";
import { SignupForm } from "@/components/auth/SignupForm";
import { Card } from "@/components/ui/Card";

export default function SignupPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
          Start the route
        </p>
        <h1 className="mt-1 mb-6 font-display text-2xl font-semibold tracking-tight text-ink">
          Create your account
        </h1>
        <SignupForm />
        <p className="mt-4 text-sm text-slate">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-ink underline decoration-blaze underline-offset-4">
            Log in
          </Link>
        </p>
      </Card>
    </div>
  );
}
