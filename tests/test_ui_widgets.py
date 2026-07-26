"""Widget tests, run headless.

These do not assert on appearance. They cover the logic the rest of the app
depends on — extension filtering, the file_loaded signal, and the log console
tolerating whatever it is handed — which is enough to catch a rename or an
import error before a user hits it.
"""

from __future__ import annotations

import os

import pytest

# Must be set before QApplication exists, so CI needs no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.widgets.drop_zone import DropZone      # noqa: E402
from ui.widgets.log_console import LogConsole  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    """One QApplication for the module — Qt permits only a single instance."""
    return QApplication.instance() or QApplication([])


# ── LogConsole ─────────────────────────────────────────────────────────────
def test_log_console_records_every_level(qt_app):
    console = LogConsole()
    for level in ("info", "success", "warning", "error"):
        console.append_log(level, f"a {level} message")
    text = console.toPlainText()
    assert "a warning message" in text
    assert "an error message" not in text      # sanity: no phantom content
    assert "a error message" in text


def test_log_console_tolerates_an_unknown_level(qt_app):
    """Logging must never crash the UI, whatever level string arrives."""
    console = LogConsole()
    console.append_log("banana", "unexpected level")
    assert "unexpected level" in console.toPlainText()


def test_log_console_tolerates_an_empty_message(qt_app):
    LogConsole().append_log("info", "")


# ── DropZone ───────────────────────────────────────────────────────────────
def test_drop_zone_stores_its_configuration(qt_app):
    zone = DropZone([".step", ".stp"], "Drop STEP file here")
    assert zone.placeholder_text == "Drop STEP file here"
    assert zone.current_file is None


def test_drop_zone_normalises_extensions_to_lowercase(qt_app):
    zone = DropZone([".STEP", ".Stp"], "Drop here")
    assert zone.accepted_extensions == [".step", ".stp"]


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("part.step", True),
        ("part.stp", True),
        ("PART.STEP", True),        # case-insensitive matching
        ("drawing.pdf", False),
        ("noextension", False),
        ("archive.step.zip", False),
    ],
)
def test_drop_zone_extension_matching(qt_app, filename, expected):
    zone = DropZone([".step", ".stp"], "Drop here")
    assert zone._matches(filename) is expected


def test_drop_zone_emits_file_loaded(qt_app):
    zone = DropZone([".step"], "Drop here")
    received: list[str] = []
    zone.file_loaded.connect(received.append)

    zone._set_file("/tmp/part.step")

    assert received == ["/tmp/part.step"]
    assert zone.current_file == "/tmp/part.step"


def test_drop_zone_clear_resets_state(qt_app):
    zone = DropZone([".step"], "Drop here")
    zone._set_file("/tmp/part.step")
    zone.clear()
    assert zone.current_file is None


def test_drop_zone_filter_string_lists_extensions(qt_app):
    zone = DropZone([".step", ".stp"], "Drop here")
    filter_string = zone._filter_string()
    assert "*.step" in filter_string
    assert "*.stp" in filter_string
