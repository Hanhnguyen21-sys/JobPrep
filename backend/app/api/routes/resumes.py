"""Resume routes.

Two ways in (paste text, upload a resume file for OCR) converge on the
same pipeline: get plain resume text from somewhere, run it through
extract_skills() (services/skill_extraction.py, text in / structured
result out, unaware of where the text came from), then persist via
_sync_resume_skills -- the shared helper both routes call, so there's
exactly one place that turns a SkillExtractionResult into Skill/user_skill
rows, not two copies that could drift.

    manual text ─────────────┐
                              ▼
    file upload -> OCR -> resume_text -> extract_skills() -> _sync_resume_skills()

"File upload" covers both images (PNG/JPG/JPEG, OCR'd directly) and PDFs
(rendered to page images first, then OCR'd the same way) -- see
services/resume_ocr.py for why a PDF needs a render step Pillow alone
can't do.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import BadRequestException
from app.db.session import get_db
from app.models.skill import Skill
from app.models.user import User, user_skill
from app.repositories.skills import get_or_create_skill
from app.schemas.resume import ResumeSkillsResponse, ResumeSubmit, SkillWithContext
from app.services.resume_ocr import (
    MIN_TEXT_LENGTH,
    extract_text_from_image,
    extract_text_from_pdf,
)
from app.services.skill_extraction import (
    ExtractedSkill,
    SkillExtractionResult,
    extract_skills,
)

router = APIRouter(prefix="/resumes", tags=["resumes"])

RESUME_ORIGIN = "resume"

# Deliberately small -- a resume file doesn't need to be huge, and this
# bounds how much memory/CPU one upload can spend on OCR (a multi-page
# PDF included -- extract_text_from_pdf separately caps page *count*, this
# caps raw upload *size*).
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
ALLOWED_PDF_EXTENSION = ".pdf"
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + (ALLOWED_PDF_EXTENSION,)
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}


def _set_target_position(db: Session, current_user: User, target_position: str) -> None:
    """Committed on its own, before extraction runs -- so it's saved even
    if skill extraction/sync fails partway through afterward. Without this
    own commit, setting the attribute here wouldn't help: everything
    shares one transaction that only reaches db.commit() at the very end,
    so an exception from extract_skills() would roll this back along with
    everything else, silently losing a position the user actually typed.
    """
    current_user.target_position = target_position.strip()
    db.commit()
    db.refresh(current_user)


def _upsert_user_skill(db: Session, user_id, skill_id, item: ExtractedSkill) -> None:
    """Link `user_id` to `skill_id`, refreshing confidence/evidence/source
    (and origin) if the link already exists.
    """
    stmt = pg_insert(user_skill).values(
        user_id=user_id,
        skill_id=skill_id,
        confidence=item.confidence,
        evidence=item.evidence,
        source=item.source,
        origin=RESUME_ORIGIN,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[user_skill.c.user_id, user_skill.c.skill_id],
        set_={
            "confidence": stmt.excluded.confidence,
            "evidence": stmt.excluded.evidence,
            "source": stmt.excluded.source,
            "origin": stmt.excluded.origin,
        },
    )
    db.execute(stmt)


def _sync_resume_skills(
    db: Session, current_user: User, result: SkillExtractionResult
) -> ResumeSkillsResponse:
    """Turns one SkillExtractionResult into Skill/user_skill rows for
    `current_user` and returns the response shape both the manual-text and
    image-upload routes return. Shared so there's one implementation of
    "how a resume's extracted skills get persisted," not one per input
    method -- see module docstring.
    """
    # Merge technical + soft into one (category, item) stream, deduping by
    # name in case the model returns the same skill in both lists —
    # technical wins on a collision since it's processed first.
    by_name: dict[str, tuple[str, ExtractedSkill]] = {}
    for item in result.technical_skills:
        by_name.setdefault(item.skill.strip().lower(), ("technical", item))
    for item in result.soft_skills:
        by_name.setdefault(item.skill.strip().lower(), ("soft", item))

    # Resolve every extracted skill to a `Skill` row *before* touching
    # user_skill, so we know the full set of skill_ids this resume
    # produced up front — needed to compute what should be removed below.
    resolved: list[tuple[Skill, ExtractedSkill]] = [
        (get_or_create_skill(db, item.skill, category), item)
        for category, item in by_name.values()
    ]

    new_skill_ids = {skill.id for skill, _ in resolved}

    # Drop resume-derived links this submission no longer supports.
    existing_resume_skill_ids = set(
        db.scalars(
            select(user_skill.c.skill_id).where(
                user_skill.c.user_id == current_user.id,
                user_skill.c.origin == RESUME_ORIGIN,
            )
        )
    )
    # find difference between old_skill_set and new_skill_set
    # drop/delete diference
    stale_skill_ids = existing_resume_skill_ids - new_skill_ids
    if stale_skill_ids:
        db.execute(
            delete(user_skill).where(
                user_skill.c.user_id == current_user.id,
                user_skill.c.skill_id.in_(stale_skill_ids),
            )
        )

    # Add/refresh every link this submission does support.
    response_skills: list[SkillWithContext] = []
    for skill, item in resolved:
        _upsert_user_skill(db, current_user.id, skill.id, item)
        response_skills.append(
            SkillWithContext(
                id=skill.id,
                name=skill.name,
                category=skill.category,
                confidence=item.confidence,
                evidence=item.evidence,
                source=item.source,
            )
        )

    db.commit()

    return ResumeSkillsResponse(skills=response_skills)


@router.post("/extract-skills", response_model=ResumeSkillsResponse)
def submit_resume(
    payload: ResumeSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeSkillsResponse:
    _set_target_position(db, current_user, payload.target_position)
    result = extract_skills(payload.text)
    return _sync_resume_skills(db, current_user, result)


@router.post("/extract-skills-from-file", response_model=ResumeSkillsResponse)
def submit_resume_file(
    target_position: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeSkillsResponse:
    """Same pipeline as submit_resume(), just with OCR (services/
    resume_ocr.py) standing in for "paste text" as the way resume_text
    gets produced. Everything after that -- extract_skills(),
    persistence -- is the exact same code, not a second implementation.

    Dispatches to extract_text_from_pdf or extract_text_from_image by
    extension -- both return the same "plain text" shape, so nothing past
    this point needs to know which one ran.
    """
    filename = file.filename or ""
    lower_filename = filename.lower()
    extension_ok = lower_filename.endswith(ALLOWED_EXTENSIONS)
    content_type_ok = file.content_type in ALLOWED_CONTENT_TYPES
    if not (extension_ok and content_type_ok):
        raise BadRequestException(
            "Unsupported file type -- please upload a PNG, JPG/JPEG image, or a PDF."
        )

    raw = file.file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise BadRequestException(
            f"That file is too large -- please upload one under "
            f"{MAX_FILE_BYTES // (1024 * 1024)} MB."
        )

    if lower_filename.endswith(ALLOWED_PDF_EXTENSION):
        resume_text = extract_text_from_pdf(raw)
    else:
        resume_text = extract_text_from_image(raw)

    if len(resume_text.strip()) < MIN_TEXT_LENGTH:
        raise BadRequestException(
            "We couldn't detect enough text in this file. Try uploading "
            "a clearer resume image/PDF or paste the resume text instead."
        )

    _set_target_position(db, current_user, target_position)
    result = extract_skills(resume_text)
    return _sync_resume_skills(db, current_user, result)