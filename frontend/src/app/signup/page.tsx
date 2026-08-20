import Link from "next/link";
import { SignupForm } from "@/components/auth/SignupForm";
import { Card } from "@/components/ui/Card";

export default function SignupPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <h1 className="mb-6 text-xl font-semibold">Create your account</h1>
        <SignupForm />
        <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium underline">
            Log in
          </Link>
        </p>
      </Card>
    </div>
  );
}
