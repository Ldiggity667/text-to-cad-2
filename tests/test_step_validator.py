"""STEP validation — the gate that stops an empty file counting as a success."""

from __future__ import annotations

import pytest

from core.step_validator import StepValidator

MINIMAL_STEP_HEADER = (
    "ISO-10303-21;\n"
    "HEADER;\n"
    "FILE_DESCRIPTION((''),'2;1');\n"
    "FILE_NAME('output.step','2026-01-01T00:00:00',(''),(''),'','','');\n"
    "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    "ENDSEC;\n"
    "DATA;\n"
    "ENDSEC;\n"
    "END-ISO-10303-21;\n"
)


@pytest.fixture
def validator() -> StepValidator:
    return StepValidator()


def test_missing_file_is_invalid(validator, tmp_path):
    ok, message = validator.validate(tmp_path / "nope.step")
    assert ok is False
    assert "does not exist" in message


def test_empty_file_is_invalid(validator, tmp_path):
    path = tmp_path / "empty.step"
    path.write_bytes(b"")
    ok, message = validator.validate(path)
    assert ok is False
    assert "empty" in message


def test_non_step_content_is_invalid(validator, tmp_path):
    """A model that wrote a text file instead of geometry must not pass."""
    path = tmp_path / "not_really.step"
    path.write_text("Sorry, I could not generate that part.", encoding="utf-8")
    ok, message = validator.validate(path)
    assert ok is False
    assert "valid STEP" in message


def test_geometry_free_file_is_rejected(validator, tmp_path):
    """A valid header with an empty DATA section must not count as a pass.

    Regression: this file imports cleanly — build123d raises nothing and
    returns a non-None object — so the validator reported success on a
    STEP containing no part at all. That is precisely the "the script ran
    and produced nothing" case the pipeline relies on this to catch.
    """
    path = tmp_path / "header_only.step"
    path.write_text(MINIMAL_STEP_HEADER, encoding="utf-8")
    ok, message = validator.validate(path)
    assert ok is False
    assert "no solid geometry" in message


def test_accepts_a_real_generated_step(validator, tmp_path):
    """Round-trip: build a solid, export it, and validate the result."""
    build123d = pytest.importorskip("build123d")

    path = tmp_path / "cube.step"
    with build123d.BuildPart() as part:
        build123d.Box(10, 10, 10)
    build123d.export_step(part.part, str(path))

    ok, message = validator.validate(path)
    assert ok is True, message
    assert "Valid STEP file" in message
