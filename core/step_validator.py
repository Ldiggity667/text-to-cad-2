"""Forge3D — STEP file validator.

Sanity-checks a generated STEP file and confirms build123d can re-import it.
"""

from __future__ import annotations

from pathlib import Path


_MAX_SIZE_BYTES = 500 * 1024 * 1024   # 500 MB


class StepValidator:
    """Validate a STEP file's existence, header, size, and re-importability."""

    def validate(self, step_path: Path) -> tuple[bool, str]:
        step_path = Path(step_path)

        # 1. Exists.
        if not step_path.exists():
            return False, "STEP file does not exist"

        size = step_path.stat().st_size

        # 2. Non-empty.
        if size == 0:
            return False, "STEP file is empty"

        # 3. Not absurdly large.
        if size > _MAX_SIZE_BYTES:
            return False, "STEP file is unexpectedly large"

        # 4. Header check.
        try:
            with open(step_path, "rb") as f:
                head = f.read(200)
            head_text = head.decode("ascii", errors="ignore")
        except OSError as e:
            return False, f"Could not read STEP file: {e}"
        if "ISO-10303" not in head_text and "STEP" not in head_text.upper():
            return False, "File does not appear to be a valid STEP file"

        # 5. Re-import with build123d.
        try:
            from build123d import import_step

            imported = import_step(str(step_path))
            if imported is None:
                return False, "STEP file imported as None — geometry may be empty"
        except Exception as e:
            return False, f"STEP reimport failed: {e}"

        # 6. Confirm the file actually contains a part.
        #
        # A STEP file with a valid header and an empty DATA section imports
        # without raising, so "it imported" is not the same as "it contains
        # geometry". This is the failure the pipeline most needs to catch:
        # a generated script that ran to completion and exported nothing.
        #
        # Volume is the direct measure; solid count is the fallback if this
        # build123d version does not expose it. If neither can be resolved,
        # the file is accepted rather than rejected over a missing attribute.
        has_geometry = None
        try:
            has_geometry = float(imported.volume) > 0
        except Exception:
            try:
                has_geometry = len(imported.solids()) > 0
            except Exception:
                has_geometry = None

        if has_geometry is False:
            return False, "STEP file imported but contains no solid geometry"

        if has_geometry is None:
            return True, f"Valid STEP file, {size // 1024} KB (geometry not verified)"

        return True, f"Valid STEP file, {size // 1024} KB"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        ok, msg = StepValidator().validate(Path(sys.argv[1]))
        print(ok, "-", msg)
    else:
        print("Usage: python step_validator.py <step_path>")
