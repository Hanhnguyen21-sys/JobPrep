"use client";

import Link from "next/link";
import { ExtractedSkillsList } from "@/components/resume/ExtractedSkillsList";
import { ResumeForm } from "@/components/resume/ResumeForm";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useResume } from "@/hooks/useResume";

export default function ResumePage() {
  const { skills, loading, error, submitResume } = useResume();

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      <div>
        <h1 className="text-xl font-semibold">Resume</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Tell us the position you&apos;re after and paste your resume text
          below. We&apos;ll pull out your skills so you can match against
          jobs next.
        </p>
      </div>

      <Card>
        <ResumeForm onSubmit={submitResume} loading={loading} error={error} />
      </Card>

      {skills.length > 0 && (
        <Card className="space-y-4">
          <ExtractedSkillsList skills={skills} />
          <Link href="/jobs">
            <Button variant="secondary">Find matching jobs →</Button>
          </Link>
        </Card>
      )}
    </div>
  );
}
