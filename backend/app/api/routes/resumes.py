

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.skill import Skill
from app.models.user import User, user_skill
from app.repositories.skills import get_or_create_skill
from app.schemas.resume import ResumeSkillsResponse, ResumeSubmit, SkillWithContext
from app.services.skill_extraction import ExtractedSkill, extract_skills

router = APIRouter(prefix="/resumes", tags=["resumes"])

RESUME_ORIGIN = "resume"


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


@router.post("/extract-skills", response_model=ResumeSkillsResponse)
def submit_resume(
    payload: ResumeSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeSkillsResponse:
    # Committed on its own, before extraction runs -- so it's saved even if
    # skill extraction/sync fails partway through below. Without this own
    # commit, setting the attribute here wouldn't help: everything shares
    # one transaction that only reaches db.commit() at the very end, so an
    # exception from extract_skills() would roll this back along with
    # everything else, silently losing a position the user actually typed.
    current_user.target_position = payload.target_position.strip()
    db.commit()
    db.refresh(current_user)

    result = extract_skills(payload.text)

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