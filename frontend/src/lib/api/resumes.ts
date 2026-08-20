import { apiFetch } from "@/lib/api/client";
import type { Skill } from "@/types/skill";

interface ResumeSkillsResponse {
  skills: Skill[];
}

// Submits resume text + target position to POST /resumes/extract-skills
// and returns the skills now linked to the current user. Mirrors
// ResumeSubmit / ResumeSkillsResponse in backend/app/schemas/resume.py --
// target_position is required on both sides now.
export async function extractSkillsFromResume(
  text: string,
  targetPosition: string,
): Promise<Skill[]> {
  const response = await apiFetch<ResumeSkillsResponse>("/resumes/extract-skills", {
    method: "POST",
    body: JSON.stringify({ text, target_position: targetPosition }),
  });

  return response.skills;
}
