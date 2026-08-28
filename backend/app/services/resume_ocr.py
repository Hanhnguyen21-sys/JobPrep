

import io

import pytesseract
from pdf2image import convert_from_bytes
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)
from PIL import Image, UnidentifiedImageError

from app.core.exceptions import BadRequestException

# Below this many non-whitespace characters, treat the OCR result as
# "couldn't read this image" rather than sending near-nothing to the
# skill-extraction LLM -- see api/routes/resumes.py's use of this.
MIN_TEXT_LENGTH = 20

# Resumes are short documents -- this bounds worst-case OCR time/cost on a
# PDF someone uploads by mistake (e.g. a 40-page ebook), same reasoning as
# every other per-run cap already in this codebase (extraction_limit_per_
# company, etc.). A resume is 1-2 pages in the overwhelming majority of
# cases; pages past this are simply not read.
MAX_PDF_PAGES = 5


def _ocr_image(image: Image.Image) -> str:
    """Shared OCR step for both entry points below. Converts to grayscale
    first -- a cheap, standard preprocessing step that generally improves
    Tesseract's accuracy on photographed/scanned documents without
    needing any per-image tuning.
    """
    grayscale = image.convert("L")

    try:
        return pytesseract.image_to_string(grayscale)
    except pytesseract.TesseractError as exc:
        raise BadRequestException(
            "Couldn't process that image for text. Try a clearer image, "
            "or paste your resume text instead."
        ) from exc


def extract_text_from_image(file: bytes | io.BytesIO) -> str:
    """Runs local Tesseract OCR over an uploaded resume image (PNG/JPG/
    JPEG) and returns the recognized plain text (not stripped/validated
    for length -- see MIN_TEXT_LENGTH and the caller for that check,
    since "is this enough text" is a product decision for the route, not
    this service).

    Raises BadRequestException (not some Pillow/pytesseract-specific
    error) if the bytes given aren't a decodable image, or if Tesseract
    itself fails -- so the route layer doesn't need to know either
    library's exception types.
    """
    raw = file.read() if isinstance(file, io.BytesIO) else file

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()  # force full decode now, not lazily later
    except (UnidentifiedImageError, OSError) as exc:
        raise BadRequestException(
            "That file doesn't look like a valid image. Try a PNG or JPG instead."
        ) from exc

    return _ocr_image(image)


def extract_text_from_pdf(file: bytes | io.BytesIO) -> str:
    """Renders each page of an uploaded resume PDF to an image (via
    pdf2image/poppler -- see module docstring for why Pillow alone can't
    do this) and runs the same Tesseract OCR step as
    extract_text_from_image over each page, joining the results.

    Capped at MAX_PDF_PAGES -- pages beyond that are silently not read,
    same "bound the worst case" reasoning as extraction/fetch limits
    elsewhere in this codebase.

    Raises BadRequestException for a corrupt/unreadable PDF, or if
    poppler isn't installed on the host, so the route layer doesn't need
    to know pdf2image's exception types.
    """
    raw = file.read() if isinstance(file, io.BytesIO) else file

    try:
        pages = convert_from_bytes(raw, last_page=MAX_PDF_PAGES)
    except PDFInfoNotInstalledError as exc:
        raise BadRequestException(
            "PDF processing isn't available on this server right now. "
            "Try uploading a PNG/JPG image instead, or paste the resume text."
        ) from exc
    except (PDFPageCountError, PDFSyntaxError) as exc:
        raise BadRequestException(
            "That file doesn't look like a valid PDF. Try a PNG/JPG image instead."
        ) from exc

    return "\n\n".join(_ocr_image(page) for page in pages)
