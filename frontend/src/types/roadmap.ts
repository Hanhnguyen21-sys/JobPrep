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

export interface PrioritySkill {
  skill: string;
  // 0-100 datapoints the priority-skills gap chart plots -- see
  // RoadmapViewer / PrioritySkillsChart. current_level is the candidate's
  // estimated existing proficiency, target_level what the selected
  // postings expect.
  current_level: number;
  target_level: number;
}

export interface RoadmapOverview {
  headline: string;
  priority_skills: PrioritySkill[];
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
  // {"<step order>": [<action_item index>, ...]} -- which action items are
  // checked off, keyed by RoadmapStep.order. {} if nothing's checked yet.
  // See backend/app/models/roadmap.py's Roadmap.completed_action_items and
  // hooks/useRoadmapProgress.ts, which is what actually reads/writes this.
  completed_action_items: Record<string, number[]>;
  // Which step (RoadmapStep.order) the user most recently checked/unchecked
  // an action item on -- see backend/app/models/roadmap.py's
  // Roadmap.last_interacted_step_order. null if nothing's ever been
  // interacted with. Drives the Dashboard's "current phase" card
  // (components/dashboard/ActiveRoadmap.tsx) instead of always showing the
  // earliest incomplete step.
  last_interacted_step_order: number | null;
}
