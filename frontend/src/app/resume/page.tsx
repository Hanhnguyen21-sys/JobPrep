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
    <div className="theme-brand flex-1 bg-paper text-ink">
      <div className="mx-auto w-full max-w-6xl space-y-8 p-6 sm:p-8">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
            Step 1
          </p>
          <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight text-brand">
            Resume
          </h1>
          <p className="mt-1 text-sm text-slate">
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
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-slate">
              Extracted skills
            </p>
            <ExtractedSkillsList skills={skills} />
            <Link href="/jobs">
              <Button variant="secondary">Find matching jobs →</Button>
            </Link>
          </Card>
        )}
      </div>
    </div>
  );
}
