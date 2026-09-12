import { apiFetch } from "@/lib/api/client";
import type { Skill } from "@/types/skill";

interface ResumeSkillsResponse {
  skills: Skill[];
}

// Calls GET /resumes/skills -- the skills already linked to the current
// user from their last resume submission, without requiring a fresh
// submit. Used by the Dashboard's skills section (see
// hooks/useResumeSkills.ts), unlike extractSkillsFromResume(File) below
// which only ever returns this right after a POST.
export async function getResumeSkills(): Promise<Skill[]> {
  const response = await apiFetch<ResumeSkillsResponse>("/resumes/skills");
  return response.skills;
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

// Submits a resume file (PNG/JPG/JPEG image, or a PDF) to
// POST /resumes/extract-skills-from-file for the backend to OCR (see
// backend/app/services/resume_ocr.py -- a PDF is rendered to page images
// first, then OCR'd the same way) and run through the exact same
// skill-extraction/persistence pipeline as extractSkillsFromResume above
// -- same response shape, so callers don't need to care which input
// method produced these skills.
export async function extractSkillsFromResumeFile(
  file: File,
  targetPosition: string,
): Promise<Skill[]> {
  const body = new FormData();
  body.append("file", file);
  body.append("target_position", targetPosition);

  const response = await apiFetch<ResumeSkillsResponse>(
    "/resumes/extract-skills-from-file",
    { method: "POST", body },
  );

  return response.skills;
}
