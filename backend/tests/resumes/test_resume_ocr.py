"""Tests for services/resume_ocr.py -- the OCR boundary itself.

Several tests here (the "_runs_real_" ones) exercise the real,
locally-installed Tesseract + poppler binaries end to end, since both are
available in this environment and it's valuable to know the actual
integration works, not just that our code calls the libraries correctly.
Every other test here is a pure error-handling check and doesn't depend on
either binary being installed. Route-level tests (test_resume_routes.py)
mock this module entirely, per the "don't require a real Tesseract/
poppler install for the suite" instruction -- this file is the one place
real OCR/PDF-rendering runs.
"""

import io

import pytest
from PIL import Image, ImageDraw

from app.core.exceptions import BadRequestException
from app.services.resume_ocr import extract_text_from_image, extract_text_from_pdf


def _image_with_text(text: str) -> Image.Image:
    image = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), text, fill="black")
    return image


def _png_bytes_with_text(text: str) -> bytes:
    buf = io.BytesIO()
    _image_with_text(text).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes_with_text(text: str) -> bytes:
    # Pillow can WRITE a PDF (embedding an image as a page) even though it
    # can't READ one back -- see resume_ocr.py's module docstring. This
    # gives us a real, valid single-page PDF to exercise
    # extract_text_from_pdf's actual poppler-backed rendering path.
    buf = io.BytesIO()
    _image_with_text(text).save(buf, format="PDF")
    return buf.getvalue()


def test_extract_text_from_image_runs_real_tesseract():
    text = extract_text_from_image(_png_bytes_with_text("Software Engineer"))
    assert "Software Engineer" in text


def test_extract_text_from_image_rejects_non_image_bytes():
    with pytest.raises(BadRequestException):
        extract_text_from_image(b"this is not an image")


def test_extract_text_from_image_rejects_empty_bytes():
    with pytest.raises(BadRequestException):
        extract_text_from_image(b"")


def test_extract_text_from_image_accepts_bytesio():
    buf = io.BytesIO(_png_bytes_with_text("Data Scientist"))
    text = extract_text_from_image(buf)
    assert "Data Scientist" in text


def test_extract_text_from_pdf_runs_real_poppler_and_tesseract():
    text = extract_text_from_pdf(_pdf_bytes_with_text("Machine Learning Engineer"))
    assert "Machine Learning Engineer" in text


def test_extract_text_from_pdf_rejects_non_pdf_bytes():
    with pytest.raises(BadRequestException):
        extract_text_from_pdf(b"this is not a pdf")


def test_extract_text_from_pdf_rejects_empty_bytes():
    with pytest.raises(BadRequestException):
        extract_text_from_pdf(b"")
