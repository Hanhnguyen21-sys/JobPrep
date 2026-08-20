// Mirrors backend/app/schemas/roadmap.py -- keep these two in sync by hand,
// same convention as types/job.ts / types/skill.ts.
//
// MAX_SELECTED_POSTINGS (the rule Nguyen set: a roadmap is generated from
// at most 10 selected job postings) now lives in types/job.ts -- import it
// from there directly (useJobSelection.ts, SelectionBar.tsx) rather than
// from here, mirroring schemas/roadmap.py importing it from schemas/job.py
// on the backend instead of redefining it.
//
// The backend always returns this shape -- roadmaps generated before this
// schema change (flat `summary` + `description`/`skills_to_develop` steps)
// get adapted into this shape server-side (see api/routes/roadmaps.py's
// _legacy_overview/_legacy_step), so nothing here needs to account for the
// old shape.

export type ResourceType =
  | "course"
  | "article"
  | "project"
  | "certification"
  | "tool";

export interface Resource {
  title: string;
  type: ResourceType;
  // AI-suggested, not verified against a live source -- may be wrong,
  // outdated, or absent when the model wasn't confident enough to guess.
  provider: string | null;
  url: string | null;
}

export interface RoadmapOverview {
  headline: string;
  priority_skills: string[];
  estimated_duration: string;
}

export interface RoadmapStep {
  order: number;
  title: string;
  focus_skill: string;
  skills: string[];
  why_it_matters: string;
  action_items: string[];
  resources: Resource[];
  project: string | null;
  duration: string;
  success_criteria: string[];
}

export interface RoadmapSourcePosting {
  id: string;
  company_name: string;
  title: string;
}

export interface RoadmapResponse {
  id: string;
  // Auto-generated label distinguishing this roadmap from others in
  // history (see backend/app/api/routes/roadmaps.py's _build_title).
  // null for roadmaps created before this field existed (migration 9) --
  // components should fall back to `Roadmap for ${target_position}`.
  title: string | null;
  target_position: string;
  overview: RoadmapOverview;
  steps: RoadmapStep[];
  source_postings: RoadmapSourcePosting[];
  created_at: string;
}
