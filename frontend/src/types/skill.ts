// Mirrors `SkillWithContext` in backend/app/schemas/resume.py — keep these
// two in sync by hand for now (no shared codegen yet).
export type SkillCategory = "technical" | "soft";

export interface Skill {
  id: string;
  name: string;
  category: SkillCategory;
  confidence: string;
  evidence: string;
  source: string;
}
