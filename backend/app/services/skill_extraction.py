"""Resume skill extraction.

Takes raw resume text and asks the model for technical and soft skills,
each with a confidence level, supporting evidence quoted/paraphrased from
the resume, and where in the resume it came from. Deliberately doesn't
touch the database — turning this structured result into `Skill` /
`user_skill` rows is the route layer's job (see `api/routes/resumes.py`).
Keeping this "text in, structured result out" makes it easy to unit test
(mock `get_ai_client()`, no DB needed) and easy to swap models/providers
later.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.ai_client import get_ai_client

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are a resume skill extraction system designed for students, new graduates, and early-career job seekers.

Your task is to analyze resume text and identify professional skills that the candidate can reasonably claim based on evidence in the resume.

Extract two categories of skills:

### 1. Technical Skills

Include concrete, professionally relevant skills such as:

* Programming languages: Python, Java, C++, JavaScript
* Frameworks/libraries: React, Flask, FastAPI, TensorFlow
* Databases: PostgreSQL, MySQL, MongoDB
* Tools/platforms: Git, Docker, AWS, Linux, Figma
* Computer science concepts: Data Structures and Algorithms, REST APIs, Machine Learning, Object-Oriented Programming
* Development methodologies: Agile, Scrum, Test-Driven Development
* Other domain-specific technical skills supported by the resume

### 2. Soft Skills

Extract soft skills only when there is evidence demonstrating them.

Examples include:

* Communication
* Collaboration
* Leadership
* Mentoring
* Problem Solving
* Time Management
* Adaptability
* Project Management
* Presentation
* Customer Communication

Do NOT infer vague personality traits such as:

* hardworking
* passionate
* motivated
* friendly
* intelligent
* detail-oriented

unless the resume contains strong behavioral evidence demonstrating a professionally relevant skill.

### Evidence Rules

Every extracted skill must be supported by resume content.

For technical skills:

* The skill may appear explicitly in a Skills section, project, coursework, or work experience.
* Technologies clearly demonstrated through project descriptions count even if they are not listed in a dedicated Skills section.

For soft skills:

* Prefer behavioral evidence over simple claims.

* Example:
  "Tutored students in programming and explained complex concepts"
  -> Communication, Mentoring

* Example:
  "Led a team of four students to build a full-stack application"
  -> Leadership, Collaboration

* Example:
  "Worked with designers and developers to launch..."
  -> Collaboration

Do not invent skills that cannot reasonably be supported by the resume.

### Student / New-Grad Considerations

Because candidates may have limited professional work experience, treat the following as valid evidence:

* Personal projects
* Academic projects
* Coursework
* Research
* Hackathons
* Student organizations
* Teaching or tutoring
* Volunteer experience
* Internships
* Open-source contributions

Do not penalize a candidate simply because the experience was academic rather than professional.

### Normalization

Normalize equivalent skill names into one canonical representation.

Examples:

* javascript -> JavaScript
* js -> JavaScript
* react.js -> React
* nodejs -> Node.js
* postgres -> PostgreSQL
* git/github -> Git and GitHub when both are actually demonstrated

Do not return duplicate skills.

Do not treat these as skills:

* Company names
* University names
* Job titles
* Project names
* Generic resume section headings

### Confidence

Assign each skill a confidence level:

* high: explicitly mentioned or clearly demonstrated
* medium: strongly implied by an activity or responsibility
* low: weak inference

Avoid returning low-confidence skills unless there is meaningful evidence.

### Output

Return valid JSON only, matching the provided schema. Use concise evidence
copied or closely paraphrased from the resume. Do not include explanations
outside the JSON."""


class ExtractedSkill(BaseModel):
    skill: str
    confidence: Literal["high", "medium", "low"]
    evidence: str
    source: Literal[
        "skills",
        "experience",
        "project",
        "coursework",
        "research",
        "volunteer",
        "leadership",
        "other",
    ]


class SkillExtractionResult(BaseModel):
    technical_skills: list[ExtractedSkill]
    soft_skills: list[ExtractedSkill]


def extract_skills(resume_text: str) -> SkillExtractionResult:
    """Return the structured extraction result (technical + soft skills)."""

    client = get_ai_client()

    completion = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": resume_text},
        ],
        response_format=SkillExtractionResult,
    )

    result = completion.choices[0].message.parsed

    if result is None:
        # Model refused, or output didn't fit the schema after retries —
        # treat as "found nothing" rather than crashing the request.
        return SkillExtractionResult(technical_skills=[], soft_skills=[])

    return result