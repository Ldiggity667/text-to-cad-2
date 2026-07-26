"""Quick smoke test for the three input handlers.

Run from the project root:  python core/inputs/test_handlers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.inputs.text_handler import TextHandler
from core.inputs.image_handler import ImageHandler  # noqa: F401
from core.inputs.pdf_handler import PdfHandler      # noqa: F401

# Test text handler
th = TextHandler()
result = th.prepare(
    "A mounting bracket 100x60x10mm with four 8mm diameter holes at corners"
)
print("TEXT:", result)

# Test image handler (uncomment and point at any PNG to exercise it)
# ih = ImageHandler()
# result = ih.prepare("path/to/test.png", "This is a bracket")
# print("IMAGE keys:", list(result.keys()), "b64 length:", len(result["image_b64"]))

# Test PDF handler (uncomment and point at any PDF)
# ph = PdfHandler()
# result = ph.prepare("path/to/test.pdf")
# print("PDF:", {k: v for k, v in result.items() if k != "page_image_b64"})
