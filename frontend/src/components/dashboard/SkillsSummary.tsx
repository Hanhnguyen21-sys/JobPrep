import Link from "next/link";
import { ExtractedSkillsList } from "@/components/resume/ExtractedSkillsList";
import { Card } from "@/components/ui/Card";
import type { Skill } from "@/types/skill";

interface SkillsSummaryProps {
  skills: Skill[];
  loading: boolean;
}

// The skills already extracted from the user's most recent resume
// submission (GET /resumes/skills -- see hooks/useResumeSkills.ts),
// reusing the exact same ExtractedSkillsList the /resume page shows
// right after a submission -- same grouping (technical/soft) and Badge
// styling, just fed from a read-only fetch instead of a just-completed
// POST.
export function SkillsSummary({ skills, loading }: SkillsSummaryProps) {
  if (loading) {
    return <p className="text-sm text-slate">Loading your skills...</p>;
  }

  if (skills.length === 0) {
    return (
      <Card className="text-center">
        <p className="text-sm text-slate">
          No skills on file yet —{" "}
          <Link href="/resume" className="text-ink underline decoration-blaze underline-offset-2">
            submit your resume
          </Link>{" "}
          to have us pull them out.
        </p>
      </Card>
    );
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-blaze">
          Your skills
        </p>
        <Link
          href="/resume"
          className="text-xs text-slate underline decoration-blaze underline-offset-2 hover:text-ink"
        >
          Update resume →
        </Link>
      </div>
      <ExtractedSkillsList skills={skills} />
    </Card>
  );
}
