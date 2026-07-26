"""Forge3D — image input handler.

Prepares an image/sketch file for the vision pipeline: validate, normalise,
resize, JPEG-encode, base64. Does NOT call Ollama.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image


SUPPORTED_FORMATS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]
MAX_DIMENSION_PX = 1024      # resize if larger
MAX_FILE_SIZE_MB = 10


class ImageHandler:
    """Prepare an image file for the vision model."""

    def prepare(self, file_path: str | Path, user_hint: str = "") -> dict:
        path = Path(file_path)

        # 1. Validate existence + extension.
        if not path.exists() or not path.is_file():
            raise ValueError(f"Image file not found: {path}")
        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported image format '{ext}'. "
                f"Supported: {', '.join(SUPPORTED_FORMATS)}"
            )

        # 2. Validate file size.
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"Image is too large ({size_mb:.1f} MB). "
                f"Maximum is {MAX_FILE_SIZE_MB} MB."
            )

        # 3-4. Open and convert to RGB.
        try:
            img = Image.open(path)
            img = img.convert("RGB")
        except Exception as e:
            raise ValueError(f"Could not open image: {e}") from e

        original_format = (Image.open(path).format or ext.lstrip(".").upper())

        # 5. Resize if needed, keeping aspect ratio.
        w, h = img.size
        if max(w, h) > MAX_DIMENSION_PX:
            scale = MAX_DIMENSION_PX / max(w, h)
            new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        final_w, final_h = img.size

        # 6. Encode as JPEG for consistent output.
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)

        # 7. Base64 encode.
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            "type": "image",
            "image_b64": image_b64,
            "original_path": str(path),
            "dimensions": (final_w, final_h),
            "format": original_format,
            "user_hint": user_hint,
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        ih = ImageHandler()
        result = ih.prepare(sys.argv[1], "test")
        print({k: (v if k != "image_b64" else f"<{len(v)} chars>")
               for k, v in result.items()})
    else:
        print("Usage: python image_handler.py <image_path>")
