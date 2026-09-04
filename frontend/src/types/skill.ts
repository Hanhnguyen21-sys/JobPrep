// Mirrors `SkillWithContext` in backend/app/schemas/resume.py — keep these
// two in sync by hand for now (no shared codegen yet).
export type SkillCategory = "technical" | "soft";

export type ProficiencyConfidence = "low" | "medium" | "high";

export interface Skill {
  id: string;
  name: string;
  category: SkillCategory;
  proficiency_level: number;
  proficiency_confidence: ProficiencyConfidence;
}
