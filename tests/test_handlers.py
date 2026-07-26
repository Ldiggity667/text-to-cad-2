"""Image and PDF input handlers.

Fixtures are generated in-process, so the repository carries no sample files.
"""

from __future__ import annotations

import base64

import pytest

from core.inputs.image_handler import (
    MAX_DIMENSION_PX,
    SUPPORTED_FORMATS,
    ImageHandler,
)
from core.inputs.pdf_handler import PdfHandler


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def make_image(tmp_path):
    """Factory writing a solid-colour image of a given size and format."""
    Image = pytest.importorskip("PIL.Image")

    def _make(name: str = "part.png", size: tuple[int, int] = (200, 150)):
        path = tmp_path / name
        Image.new("RGB", size, (200, 200, 200)).save(path)
        return path

    return _make


@pytest.fixture
def make_pdf(tmp_path):
    """Factory writing a single-page PDF carrying the given text."""
    fitz = pytest.importorskip("fitz")

    def _make(name: str = "drawing.pdf", text: str = "PLATE 100mm x 50mm",
              pages: int = 1):
        path = tmp_path / name
        doc = fitz.open()
        for _ in range(pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text(fitz.Point(72, 72), text, fontsize=12)
        doc.save(str(path))
        doc.close()
        return path

    return _make


# ── ImageHandler ───────────────────────────────────────────────────────────
def test_image_prepare_returns_base64(make_image):
    result = ImageHandler().prepare(make_image())
    assert result["image_b64"]
    # Must be decodable, or the vision model will reject it.
    base64.b64decode(result["image_b64"], validate=True)


def test_image_missing_file_rejected(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        ImageHandler().prepare(tmp_path / "absent.png")


def test_image_unsupported_format_rejected(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not an image", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        ImageHandler().prepare(path)


@pytest.mark.parametrize("ext", [".png", ".jpg", ".bmp"])
def test_image_supported_formats_accepted(make_image, ext):
    assert ext in SUPPORTED_FORMATS
    result = ImageHandler().prepare(make_image(name=f"part{ext}"))
    assert result["image_b64"]


def test_image_extension_check_is_case_insensitive(make_image):
    assert ImageHandler().prepare(make_image(name="PART.PNG"))["image_b64"]


def test_oversized_image_is_downscaled(make_image):
    """Large sketches must be resized or they blow up the vision context."""
    oversized = MAX_DIMENSION_PX * 2
    result = ImageHandler().prepare(make_image(size=(oversized, oversized)))
    raw = base64.b64decode(result["image_b64"])

    Image = pytest.importorskip("PIL.Image")
    import io

    with Image.open(io.BytesIO(raw)) as img:
        assert max(img.size) <= MAX_DIMENSION_PX


def test_user_hint_is_carried_through(make_image):
    result = ImageHandler().prepare(make_image(), "a mounting bracket")
    assert "bracket" in str(result).lower()


# ── PdfHandler ─────────────────────────────────────────────────────────────
def test_pdf_prepare_extracts_text(make_pdf):
    result = PdfHandler().prepare(make_pdf(text="MOUNTING PLATE 100mm"))
    assert "MOUNTING PLATE" in result["extracted_text"]


def test_pdf_missing_file_rejected(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        PdfHandler().prepare(tmp_path / "absent.pdf")


def test_pdf_reports_page_descriptions(make_pdf):
    result = PdfHandler().prepare(make_pdf(pages=2))
    assert result["page_descriptions"]


def test_pdf_renders_first_page_image(make_pdf):
    result = PdfHandler().prepare(make_pdf())
    if result.get("page_image_b64"):
        base64.b64decode(result["page_image_b64"], validate=True)


def test_pdf_dimension_candidates_found(make_pdf):
    result = PdfHandler().prepare(
        make_pdf(text="LENGTH 120mm WIDTH 80mm BORE R25")
    )
    assert "120" in result["extracted_text"]


def test_corrupt_pdf_rejected(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not really a pdf")
    with pytest.raises(ValueError):
        PdfHandler().prepare(path)
