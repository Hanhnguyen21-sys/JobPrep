

from typing import Literal

from pydantic import BaseModel, Field

from app.core.ai_client import get_ai_client

MODEL = "gpt-4o-mini"


SYSTEM_PROMPT = """You are a career roadmap generation system for students, new graduates, and early-career job seekers.

You will be given:
- The candidate's target position.
- The job postings the candidate is specifically interested in (company + title only, for context -- not the full description).
- A precomputed skill gap: every skill required or preferred by at least one of these postings (the stricter requirement_level wins when postings disagree), each already compared against the candidate's own recorded skills. For each skill you get:
  - category: "technical" or "soft".
  - requirement_level: "required" or "preferred" across these postings.
  - has_it: whether the candidate already has this skill.
  - current_level: the candidate's real estimated proficiency (0-100) if they have it, else 0. This is already computed from their data -- use it as given, do not re-estimate or override it.
  - postings_requiring: how many of the given postings required or preferred this skill -- a count, not a boolean. This is the signal for "required by more of the given postings" below.

This comparison has already been done -- do not re-derive which skills matter or whether the candidate has them from the posting titles or your own judgment; your job is to turn this gap into a roadmap. If the skill gap is empty, fall back to reasoning from the target position and posting titles alone.

Produce ONE combined roadmap that would prepare the candidate for ALL of the given postings together -- not a separate roadmap per posting. Prioritize skills that are `required` and where `has_it` is false or `current_level` is low, since those are the actual gaps; skills the candidate already has strongly need at most a deepening step, not a from-scratch one.

Keep every field short and scannable -- one line per field unless told otherwise below. Do not write paragraphs; split what you'd normally put in one long paragraph across the separate fields described here instead.

Return:
- overview:
  - headline: one sentence on the overall gap between where the candidate is now and what these postings need.
  - priority_skills: the 3-6 highest-priority skills from the given skill gap (required over preferred, and skills the candidate is missing or weak in over ones they already have), ordered most-critical first. Each is a datapoint, not a sentence:
    - skill: the skill name as given.
    - current_level: use the given current_level exactly as provided -- do not change it.
    - target_level: 0-100 rating of the proficiency these postings expect for this skill, your judgment informed by requirement_level and category. Should be meaningfully higher than current_level for a required skill the candidate lacks; close to current_level only for a skill listed mainly to deepen.
  - estimated_duration: a short phrase for the whole plan, e.g. "2-3 months".
- steps: an ordered list of concrete milestones (typically 4-8) the candidate should work through in sequence. Each step needs:
  - order: 1-based position in the sequence.
  - title: short and specific (e.g. "Build a REST API with authentication in FastAPI or Flask", not "Learn backend").
  - focus_skill: the single most important skill this step targets, drawn from the skill gap.
  - skills: all skills/tools this step targets, drawn from the given skill gap or reasonable prerequisites for them (include focus_skill).
  - why_it_matters: one sentence on why this step matters for these specific postings.
  - action_items: 2-5 short, concrete tasks the candidate should actually do for this step (a checklist, not a paragraph).
  - resources: 1-3 specific courses, articles, projects, certifications, or tools that would help with this step. Each needs a title, a type (course/article/project/certification/tool), and a provider if there's a well-known one (e.g. "Coursera", "O'Reilly"); include a url only when you're reasonably confident it's a real, correct link for that specific resource, otherwise omit it rather than guessing.
  - project: an optional short description of a project the candidate could build to demonstrate this step's skills, or omit if a dedicated project doesn't make sense for this step.
  - duration: a short phrase for this step alone, e.g. "1-2 weeks".
  - success_criteria: 1-3 short, concrete signs the candidate has actually finished this step (how they'd know, not just "understand X").

Order steps by dependency and priority, not just posting order -- foundational skills before advanced ones, and skills required by more of the given postings generally before posting-specific ones, unless a dependency requires otherwise.

Return valid JSON only, matching the provided schema. Do not include explanations outside the JSON."""


class ResourceResult(BaseModel):
    title: str
    type: Literal["course", "article", "project", "certification", "tool"]
    provider: str | None = None
    url: str | None = None


class PrioritySkillResult(BaseModel):
    skill: str
    current_level: int = Field(ge=0, le=100)
    target_level: int = Field(ge=0, le=100)


class RoadmapOverviewResult(BaseModel):
    headline: str
    priority_skills: list[PrioritySkillResult]
    estimated_duration: str


class RoadmapStepResult(BaseModel):
    order: int
    title: str
    focus_skill: str
    skills: list[str]
    why_it_matters: str
    action_items: list[str]
    resources: list[ResourceResult] = []
    project: str | None = None
    duration: str
    success_criteria: list[str]


class RoadmapGenerationResult(BaseModel):
    overview: RoadmapOverviewResult
    steps: list[RoadmapStepResult]


def generate_roadmap(
    target_position: str,
    skill_gap: list[dict],
    postings: list[dict],
) -> RoadmapGenerationResult | None:
    """`skill_gap` is the precomputed Skill-Set-A-vs-Skill-Set-B comparison
    (api/routes/roadmaps.py::_build_skill_gap: job_posting_skill joined
    against user_skill by shared Skill.id) -- each entry already carries
    category/requirement_level/has_it/current_level/postings_requiring, so
    the model compares like-for-like instead of re-extracting skills from
    raw posting text. `postings` carries only company/title for context;
    the full description is deliberately NOT sent here (that's what
    skill_gap replaces).
    """
    client = get_ai_client()

    postings_block = "\n".join(
        f"- {posting['title']} at {posting['company_name']}" for posting in postings
    )

    gap_block = "\n".join(
        f"- {item['skill']} | category={item['category']} | "
        f"requirement_level={item['requirement_level']} | "
        f"has_it={item['has_it']} | current_level={item['current_level']} | "
        f"postings_requiring={item['postings_requiring']}"
        for item in skill_gap
    ) or "(no specific skills were extracted from these postings)"

    user_content = (
        f"Target position: {target_position}\n\n"
        f"Postings the candidate is targeting:\n{postings_block}\n\n"
        "Precomputed skill gap (already compared against the candidate's "
        f"own skills -- do not re-derive this):\n{gap_block}"
    )

    completion = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=RoadmapGenerationResult,
    )

    return completion.choices[0].message.parsed
