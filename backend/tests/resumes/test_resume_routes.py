"""Tests for api/routes/resumes.py -- the manual-text route
(submit_resume) and the file-upload route (submit_resume_file, which
accepts images and PDFs), called directly as plain functions (same
approach as the other test modules in this suite: a MagicMock
`db`/`current_user`, FastAPI's dependency injection bypassed entirely, no
real Postgres needed).

The OCR boundary (extract_text_from_image / extract_text_from_pdf) is
mocked throughout, per the requirement that this suite never depends on a
real Tesseract/poppler install -- see tests/resumes/test_resume_ocr.py for
the one place real OCR runs.
"""

import io
import uuid
from unittest.mock import MagicMock

import pytest

from app.api.routes import resumes
from app.core.exceptions import BadRequestException
from app.models.user import User
from app.services.skill_extraction import ExtractedSkill, SkillExtractionResult


def _fake_upload(filename: str, content_type: str, content: bytes = b"fake-file-bytes"):
    upload = MagicMock()
    upload.filename = filename
    upload.content_type = content_type
    upload.file = io.BytesIO(content)
    return upload


def _fake_user() -> User:
    return User(id="00000000-0000-0000-0000-000000000001", email="test@example.com")


def _assign_id_on_add(obj) -> None:
    # Mimics what a real flush() against Postgres would do (assign the
    # id default) -- get_or_create_skill's newly-created Skill needs a
    # real id for SkillWithContext to validate, and this db is a mock
    # with no real database behind it.
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = None  # get_or_create_skill: no existing skill -> creates new
    db.scalars.return_value = iter([])  # no existing resume-origin user_skill rows
    db.add.side_effect = _assign_id_on_add
    return db


def _extraction_result() -> SkillExtractionResult:
    return SkillExtractionResult(
        technical_skills=[
            ExtractedSkill(skill="Python", confidence="high", evidence="...", source="skills")
        ],
        soft_skills=[],
    )


# ---------------------------------------------------------------------------
# Manual text flow -- still works
# ---------------------------------------------------------------------------


def test_manual_text_flow_still_works(monkeypatch):
    monkeypatch.setattr(resumes, "extract_skills", lambda text: _extraction_result())

    payload = MagicMock(text="some resume text", target_position="Software Engineer")
    db = _fake_db()
    user = _fake_user()

    response = resumes.submit_resume(payload, current_user=user, db=db)

    assert response.skills[0].name == "Python"
    assert user.target_position == "Software Engineer"


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


def test_valid_png_upload_flows_into_extract_skills(monkeypatch):
    monkeypatch.setattr(
        resumes, "extract_text_from_image", lambda raw: "Python FastAPI PostgreSQL " * 5
    )
    extract_skills_calls = []

    def fake_extract_skills(text):
        extract_skills_calls.append(text)
        return _extraction_result()

    monkeypatch.setattr(resumes, "extract_skills", fake_extract_skills)

    upload = _fake_upload("resume.png", "image/png")
    db = _fake_db()
    user = _fake_user()

    response = resumes.submit_resume_file(
        target_position="Software Engineer", file=upload, current_user=user, db=db
    )

    assert response.skills[0].name == "Python"
    assert user.target_position == "Software Engineer"
    assert extract_skills_calls == ["Python FastAPI PostgreSQL " * 5]


def test_valid_jpg_upload_is_accepted(monkeypatch):
    monkeypatch.setattr(resumes, "extract_text_from_image", lambda raw: "enough text here " * 3)
    monkeypatch.setattr(resumes, "extract_skills", lambda text: _extraction_result())

    upload = _fake_upload("resume.jpg", "image/jpeg")
    response = resumes.submit_resume_file(
        target_position="Data Scientist", file=upload, current_user=_fake_user(), db=_fake_db()
    )

    assert response.skills[0].name == "Python"


# ---------------------------------------------------------------------------
# PDF upload
# ---------------------------------------------------------------------------


def test_valid_pdf_upload_dispatches_to_pdf_extractor_not_image(monkeypatch):
    image_ocr_called = False

    def fake_extract_text_from_image(raw):
        nonlocal image_ocr_called
        image_ocr_called = True
        return "should not be used"

    pdf_ocr_calls = []

    def fake_extract_text_from_pdf(raw):
        pdf_ocr_calls.append(raw)
        return "Backend Engineer Kubernetes Docker " * 3

    monkeypatch.setattr(resumes, "extract_text_from_image", fake_extract_text_from_image)
    monkeypatch.setattr(resumes, "extract_text_from_pdf", fake_extract_text_from_pdf)
    monkeypatch.setattr(resumes, "extract_skills", lambda text: _extraction_result())

    upload = _fake_upload("resume.pdf", "application/pdf", content=b"%PDF-fake-bytes")
    response = resumes.submit_resume_file(
        target_position="Backend Engineer", file=upload, current_user=_fake_user(), db=_fake_db()
    )

    assert response.skills[0].name == "Python"
    assert image_ocr_called is False
    assert pdf_ocr_calls == [b"%PDF-fake-bytes"]


def test_invalid_pdf_bytes_raise_before_reaching_extract_skills(monkeypatch):
    """extract_text_from_pdf is responsible for the "not a real PDF"
    error itself (see test_resume_ocr.py) -- here we just confirm the
    route lets that error propagate rather than swallowing it and still
    calling extract_skills.
    """

    def fake_extract_text_from_pdf(raw):
        raise BadRequestException("That file doesn't look like a valid PDF.")

    extract_skills_called = False

    def fake_extract_skills(text):
        nonlocal extract_skills_called
        extract_skills_called = True
        return _extraction_result()

    monkeypatch.setattr(resumes, "extract_text_from_pdf", fake_extract_text_from_pdf)
    monkeypatch.setattr(resumes, "extract_skills", fake_extract_skills)

    upload = _fake_upload("resume.pdf", "application/pdf")

    with pytest.raises(BadRequestException):
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )

    assert extract_skills_called is False


# ---------------------------------------------------------------------------
# Validation shared by both file types
# ---------------------------------------------------------------------------


def test_unsupported_file_type_is_rejected(monkeypatch):
    image_ocr_called = False
    pdf_ocr_called = False

    monkeypatch.setattr(
        resumes,
        "extract_text_from_image",
        lambda raw: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    monkeypatch.setattr(
        resumes,
        "extract_text_from_pdf",
        lambda raw: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    upload = _fake_upload("resume.gif", "image/gif")

    with pytest.raises(BadRequestException):
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )

    assert image_ocr_called is False
    assert pdf_ocr_called is False


def test_extension_and_content_type_are_both_checked(monkeypatch):
    """A .png filename with a mismatched content-type must still be
    rejected -- validating only one of the two would let a mislabeled
    upload slip through.
    """
    upload = _fake_upload("resume.png", "application/octet-stream")

    with pytest.raises(BadRequestException):
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )


def test_oversized_file_is_rejected(monkeypatch):
    ocr_called = False

    def fake_extract_text_from_image(raw):
        nonlocal ocr_called
        ocr_called = True
        return "text"

    monkeypatch.setattr(resumes, "extract_text_from_image", fake_extract_text_from_image)

    too_big = b"x" * (resumes.MAX_FILE_BYTES + 1)
    upload = _fake_upload("resume.png", "image/png", content=too_big)

    with pytest.raises(BadRequestException):
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )

    assert ocr_called is False


def test_empty_ocr_result_does_not_call_extract_skills(monkeypatch):
    monkeypatch.setattr(resumes, "extract_text_from_image", lambda raw: "   ")

    extract_skills_called = False

    def fake_extract_skills(text):
        nonlocal extract_skills_called
        extract_skills_called = True
        return _extraction_result()

    monkeypatch.setattr(resumes, "extract_skills", fake_extract_skills)

    upload = _fake_upload("resume.png", "image/png")

    with pytest.raises(BadRequestException) as exc_info:
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )

    assert "couldn't detect enough text" in exc_info.value.detail.lower()
    assert extract_skills_called is False


def test_near_empty_ocr_result_is_treated_as_empty(monkeypatch):
    # Below MIN_TEXT_LENGTH but non-blank -- still shouldn't reach the LLM.
    monkeypatch.setattr(resumes, "extract_text_from_image", lambda raw: "abc")

    extract_skills_called = False

    def fake_extract_skills(text):
        nonlocal extract_skills_called
        extract_skills_called = True
        return _extraction_result()

    monkeypatch.setattr(resumes, "extract_skills", fake_extract_skills)

    upload = _fake_upload("resume.png", "image/png")

    with pytest.raises(BadRequestException):
        resumes.submit_resume_file(
            target_position="Software Engineer",
            file=upload,
            current_user=_fake_user(),
            db=_fake_db(),
        )

    assert extract_skills_called is False
