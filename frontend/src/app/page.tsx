import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-6 text-center">
      <h1 className="text-3xl font-semibold">Land your next job, faster.</h1>
      <p className="max-w-md text-zinc-600 dark:text-zinc-400">
        Upload your resume, match against real job postings, and get a
        personalized roadmap to close the gap.
      </p>
      <Link href="/signup">
        <Button>Get started</Button>
      </Link>
    </div>
  );
}
