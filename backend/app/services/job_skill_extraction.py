
# extract skills from job description - also call OpenAI API
# required_skills and preferred_skills 
# compare with user' skills 
from typing import Literal

from pydantic import BaseModel

from app.core.ai_client import get_ai_client

MODEL = "gpt-4o-mini"

# How many postings go into one OpenAI call. Kept small on purpose: a
# bigger batch means fewer calls but a longer prompt and a bigger single
# point of failure (one malformed/refused response loses the whole
# batch's results, not just one posting's). 5 was picked as a reasonable
# middle ground -- tune here if that tradeoff needs to move.
BATCH_SIZE = 5

SYSTEM_PROMPT = """You are a job posting skill extraction system.

You will be given one or more job postings, each labeled with a numeric
index like "### Posting 0". Process each posting completely
independently -- skills, evidence, and categorization for one posting
must never be influenced by or mixed with another posting in the same
batch.

For each posting, identify the skills a candidate would need, split into
two groups:

- required_skills: skills stated as requirements, must-haves, or minimum
  qualifications ("must have", "required", "X+ years of experience with",
  a "Requirements" / "Minimum Qualifications" section).
- preferred_skills: skills stated as nice-to-haves ("preferred", "bonus",
  "a plus", "Nice to Have" / "Preferred Qualifications" section). If the
  posting doesn't distinguish required from preferred at all, place
  skills mentioned in the main requirements/responsibilities text under
  required_skills, not preferred_skills.

For each skill, also assign a category:

- "technical": programming languages, frameworks/libraries, databases,
  tools/platforms, CS concepts, methodologies -- concrete and verifiable.
- "soft": communication, leadership, collaboration, and similar -- only
  when the posting actually names them, not inferred from tone.

Normalize equivalent skill names into one canonical representation
(javascript/js -> JavaScript, postgres -> PostgreSQL, etc.), and do not
return duplicate skills within the same posting's lists.

Do not treat these as skills: company name, job title, team/department
names, generic section headings, or vague traits ("fast learner",
"passionate", "team player") without a concrete skill attached.

Return valid JSON only, matching the provided schema: one result object
per posting you were given, each carrying the same numeric `index` it was
labeled with in the input ("### Posting 0" -> index 0, etc.), covering
every index exactly once. Use concise evidence copied or closely
paraphrased from the posting it came from. Do not include explanations
outside the JSON."""


class ExtractedJobSkill(BaseModel):
    skill: str
    category: Literal["technical", "soft"]
    evidence: str


class JobSkillExtractionResult(BaseModel):
    required_skills: list[ExtractedJobSkill]
    preferred_skills: list[ExtractedJobSkill]


class _BatchResultItem(BaseModel):
    index: int
    required_skills: list[ExtractedJobSkill]
    preferred_skills: list[ExtractedJobSkill]


class _BatchResponse(BaseModel):
    results: list[_BatchResultItem]


def extract_job_skills(description: str) -> JobSkillExtractionResult:
    """Single-posting convenience wrapper around extract_job_skills_batch."""
    return extract_job_skills_batch([description])[0]


def extract_job_skills_batch(descriptions: list[str]) -> list[JobSkillExtractionResult]:
    
    if not descriptions:
        return []

    results = [
        JobSkillExtractionResult(required_skills=[], preferred_skills=[])
        for _ in descriptions
    ]

    client = get_ai_client()

    for start in range(0, len(descriptions), BATCH_SIZE):
        chunk = descriptions[start : start + BATCH_SIZE]
        user_content = "\n\n".join(
            f"### Posting {i}\n{description}" for i, description in enumerate(chunk)
        )

        completion = client.beta.chat.completions.parse(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=_BatchResponse,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            continue  # leave this chunk's results at the "found nothing" default

        for item in parsed.results:
            if 0 <= item.index < len(chunk):
                results[start + item.index] = JobSkillExtractionResult(
                    required_skills=item.required_skills,
                    preferred_skills=item.preferred_skills,
                )

    return results
