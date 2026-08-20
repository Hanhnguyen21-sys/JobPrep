"""Roadmap generation.

Takes the (up to MAX_SELECTED_POSTINGS, see schemas/roadmap.py) job
postings a user selected on /jobs, the user's target position, and their
current skills, and asks the model for ONE combined learning roadmap that
prepares them for all of the selected postings together -- not one roadmap
per posting. Deliberately doesn't touch the database, same "text in,
structured result out" split as services/skill_extraction.py and
services/job_skill_extraction.py; api/routes/roadmaps.py turns the result
into a `Roadmap` row.

Unlike job_skill_extraction.py's batching, this is always a single call,
never chunked -- a roadmap is one synthesis across all selected postings at
once (the model needs to see all of them together to find the skills they
share and prioritize accordingly), so there's nothing to gain by splitting
the request the way per-posting extraction does.

Output is deliberately atomized into small fields (see RoadmapStepResult
below) rather than one prose paragraph per step -- asking the model for
short, scoped fields (one line each for "why it matters", a checklist for
"what to do", a separate list for "how you'll know you're done") produces
shorter, more scannable text per field than asking it to write a paragraph
that covers all of those at once.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.ai_client import get_ai_client

MODEL = "gpt-4o-mini"

# Truncates any single posting's description before it goes into the
# prompt -- keeps one unusually long or noisy posting from blowing the
# prompt budget or crowding out the other (up to 9) postings in the same
# call. Same defensive instinct as job_skill_extraction.py's BATCH_SIZE,
# just applied to length instead of call count.
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
  - priority_skills: the 3-6 skills/tools that matter most across the selected postings, short phrases (e.g. "Distributed systems", not a sentence).
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


class RoadmapOverviewResult(BaseModel):
    headline: str
    priority_skills: list[str]
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
    """`postings` is a list of {"company_name": str, "title": str,
    "description": str | None} dicts, already limited to the user's
    selection -- this function trusts its caller (api/routes/roadmaps.py)
    to have already enforced MAX_SELECTED_POSTINGS; it doesn't re-check
    the cap itself.

    Returns None if the model refused or its output didn't fit the schema
    after retries. Unlike skill_extraction.py's "found nothing" fallback,
    there's no sane empty roadmap to silently return here -- an empty
    roadmap isn't a valid "nothing found" result, it's just broken -- so
    this pushes the decision of what to do back to the caller instead of
    manufacturing a fake empty one.
    """
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
