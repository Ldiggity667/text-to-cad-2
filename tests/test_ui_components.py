"""Import smoke tests for the UI package.

Every UI module is imported headlessly. This is deliberately shallow — its job
is to catch a syntax error, a bad import, or a module renamed without its
callers being updated, none of which should ever reach a user.
"""

from __future__ import annotations

import importlib
import os

import pytest

# Must be set before any Qt import so CI needs no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

UI_MODULES = [
    "ui.app",
    "ui.main_window",
    "ui.dialogs.settings_dialog",
    "ui.panels.history_panel",
    "ui.panels.input_panel",
    "ui.panels.preview_panel",
    "ui.widgets.drop_zone",
    "ui.widgets.log_console",
    "ui.widgets.model_selector",
]

CORE_MODULES = [
    "core",
    "core.code_runner",
    "core.ollama_client",
    "core.pipeline",
    "core.prompt_engineer",
    "core.step_validator",
    "core.inputs.image_handler",
    "core.inputs.pdf_handler",
    "core.inputs.text_handler",
]


@pytest.mark.parametrize("module_name", UI_MODULES)
def test_ui_module_imports(module_name):
    assert importlib.import_module(module_name) is not None


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports(module_name):
    assert importlib.import_module(module_name) is not None


def test_app_exposes_create_app():
    from ui.app import create_app

    assert callable(create_app)


def test_package_metadata_present():
    import core

    assert core.APP_NAME
    assert core.APP_VERSION
