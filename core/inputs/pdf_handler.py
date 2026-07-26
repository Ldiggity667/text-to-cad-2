"""Forge3D — PDF engineering-drawing handler.

Extracts text + a rasterised first-page image from a technical drawing PDF and
mines it for dimension candidates and view descriptions. Does NOT call Ollama.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import fitz  # PyMuPDF


RASTER_DPI = 150
MAX_PAGES_TO_PROCESS = 4   # most drawings are 1-2 pages; cap at 4

# Numbers with units, or Ø<n> (diameter), or R<n> (radius).
_DIMENSION_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*(?:mm|cm|m|in|inch|"|\')'
    r'|\bØ\s*(\d+(?:\.\d+)?)'
    r'|\bR\s*(\d+(?:\.\d+)?)'
)

_VIEW_KEYWORDS = ["FRONT", "TOP", "SIDE", "SECTION", "DETAIL", "SCALE"]


class PdfHandler:
    """Prepare a PDF drawing for the generation pipeline."""

    def prepare(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"PDF file not found: {path}")

        try:
            doc = fitz.open(str(path))
        except Exception as e:
            raise ValueError(f"Could not open PDF: {e}") from e

        try:
            if doc.needs_pass:
                raise ValueError("PDF is encrypted/password-protected.")

            page_count = doc.page_count
            if page_count < 1:
                raise ValueError("PDF has no pages.")

            pages_to_process = min(page_count, MAX_PAGES_TO_PROCESS)

            page_texts: list[str] = []
            page_descriptions: list[str] = []
            first_page_png: bytes | None = None

            for i in range(pages_to_process):
                page = doc.load_page(i)

                # a. Extract + normalise text.
                text = page.get_text("text") or ""
                text = re.sub(r"[ \t]+", " ", text).strip()
                page_texts.append(text)

                # b. Rasterise.
                mat = fitz.Matrix(RASTER_DPI / 72, RASTER_DPI / 72)
                pix = page.get_pixmap(matrix=mat)
                if i == 0:
                    first_page_png = pix.tobytes("png")

                # View description for this page.
                upper = text.upper()
                found = [kw for kw in _VIEW_KEYWORDS if kw in upper]
                parts = []
                if found:
                    parts.append(", ".join(f"{kw} VIEW" if kw in
                                 ("FRONT", "TOP", "SIDE") else kw for kw in found))
                if _DIMENSION_RE.search(text):
                    parts.append("dimension annotations")
                desc = f"Page {i + 1}: " + (
                    "; ".join(parts) if parts else "no recognised views/dimensions"
                )
                page_descriptions.append(desc)

            # 5. Combine page texts.
            combined = []
            for i, t in enumerate(page_texts):
                combined.append(f"--- Page {i + 1} ---")
                combined.append(t)
            extracted_text = "\n\n".join(combined).strip()

            # 6. First-page image → base64.
            page_image_b64 = (
                base64.b64encode(first_page_png).decode("utf-8")
                if first_page_png else None
            )

            # 7. Dimension candidates across all processed pages.
            dimension_candidates: list[str] = []
            for m in _DIMENSION_RE.finditer(extracted_text):
                dimension_candidates.append(m.group(0).strip())

            return {
                "type": "pdf",
                "extracted_text": extracted_text,
                "page_count": page_count,
                "pages_processed": pages_to_process,
                "page_image_b64": page_image_b64,
                "page_descriptions": page_descriptions,
                "has_dimensions": len(dimension_candidates) > 0,
                "dimension_candidates": dimension_candidates,
            }
        finally:
            doc.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        ph = PdfHandler()
        result = ph.prepare(sys.argv[1])
        print({k: (v if k != "page_image_b64" else
                   (f"<{len(v)} chars>" if v else None))
               for k, v in result.items()})
    else:
        print("Usage: python pdf_handler.py <pdf_path>")
