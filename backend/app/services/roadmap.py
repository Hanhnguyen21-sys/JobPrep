

from typing import Literal

from pydantic import BaseModel

from app.core.ai_client import get_ai_client

MODEL = "gpt-4o-mini"


MAX_DESCRIPTION_CHARS = 6_000

SYSTEM_PROMPT = """You are a career roadmap generation system for students, new graduates, and early-career job seekers.

You will be given:
- The candidate's target position.
- The skills the candidate already has (may be empty).
- One or more real job postings the candidate is specifically interested in, each labeled with a numeric index like "### Posting 0", including company, title, and full description.

Produce ONE combined roadmap that would prepare the candidate for ALL of the given postings together -- not a separate roadmap per posting. Look across every posting for the skills, tools, and qualifications that are shared or come up repeatedly, and prioritize those, since closing those gaps helps with the most postings at once. Still incorporate posting-specific requirements where they matter, but don't just concatenate each posting's requirements into an unstructured list.

Do not present skills the candidate already has as things they still need to develop from scratch, but you may include a step that deepens an existing skill if the postings call for a stronger level of it than the evidence supports.

Keep every field short and scannable -- one line per field unless told otherwise below. Do not write paragraphs; split what you'd normally put in one long paragraph across the separate fields described here instead.

Return:
- overview:
  - headline: one sentence on the overall gap between where the candidate is now and what these postings need.
  - priority_skills: the 3-6 skills/tools that matter most across the selected postings, ordered most-critical first. Each is a datapoint, not a sentence:
    - skill: short phrase (e.g. "Distributed systems", not a sentence).
    - current_level: 0-100 rating of the candidate's existing proficiency in this skill, estimated from their listed skills/evidence. 0 if they don't have it at all; don't round every value to a multiple of 10 -- use the full range so skills at genuinely different levels don't collide.
    - target_level: 0-100 rating of the proficiency these postings expect for this skill. Should be meaningfully higher than current_level for a skill that's actually a gap; close to current_level only for a skill listed mainly to deepen.
  - estimated_duration: a short phrase for the whole plan, e.g. "2-3 months".
- steps: an ordered list of concrete milestones (typically 4-8) the candidate should work through in sequence. Each step needs:
  - order: 1-based position in the sequence.
  - title: short and specific (e.g. "Build a REST API with authentication in FastAPI or Flask", not "Learn backend").
  - focus_skill: the single most important skill this step targets.
  - skills: all skills/tools this step targets, drawn from the postings' required/preferred skills or reasonable prerequisites for them (include focus_skill).
  - why_it_matters: one sentence on why this step matters for these specific postings.
  - action_items: 2-5 short, concrete tasks the candidate should actually do for this step (a checklist, not a paragraph).
  - resources: 1-3 specific courses, articles, projects, certifications, or tools that would help with this step. Each needs a title, a type (course/article/project/certification/tool), and a provider if there's a well-known one (e.g. "Coursera", "O'Reilly"); include a url only when you're reasonably confident it's a real, correct link for that specific resource, otherwise omit it rather than guessing.
  - project: an optional short description of a project the candidate could build to demonstrate this step's skills, or omit if a dedicated project doesn't make sense for this step.
  - duration: a short phrase for this step alone, e.g. "1-2 weeks".
  - success_criteria: 1-3 short, concrete signs the candidate has actually finished this step (how they'd know, not just "understand X").

Order steps by dependency and priority, not just posting order -- foundational skills before advanced ones, and skills shared across more postings generally before posting-specific ones, unless a dependency requires otherwise.

Return valid JSON only, matching the provided schema. Do not include explanations outside the JSON."""


class ResourceResult(BaseModel):
    title: str
    type: Literal["course", "article", "project", "certification", "tool"]
    provider: str | None = None
    url: str | None = None


class PrioritySkillResult(BaseModel):
    skill: str
    current_level: int
    target_level: int


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
    existing_skills: list[str],
    postings: list[dict],
) -> RoadmapGenerationResult | None:
    
    client = get_ai_client()

    postings_block = "\n\n".join(
        f"### Posting {i}\n"
        f"Company: {posting['company_name']}\n"
        f"Title: {posting['title']}\n"
        f"Description:\n{(posting.get('description') or '')[:MAX_DESCRIPTION_CHARS]}"
        for i, posting in enumerate(postings)
    )

    user_content = (
        f"Target position: {target_position}\n"
        "Candidate's current skills: "
        f"{', '.join(existing_skills) if existing_skills else '(none recorded yet)'}\n\n"
        f"{postings_block}"
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
