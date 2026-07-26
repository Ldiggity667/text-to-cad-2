"""Forge3D — Ollama model selector widget."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from core.ollama_client import OllamaClient


_VISION_HINTS = ("llava", "vision", "vl", "gemma3", "bakllava", "moondream")
_NOT_RUNNING = "Ollama not running"


class ModelSelector(QWidget):
    """Two combos (text + vision) populated from the local Ollama server."""

    text_model_changed = Signal(str)
    vision_model_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Forge3D", "Forge3D")

        layout = QFormLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.text_model_combo = QComboBox()
        self.vision_model_combo = QComboBox()
        self.text_model_combo.setMinimumWidth(160)
        self.vision_model_combo.setMinimumWidth(160)

        text_row = QHBoxLayout()
        text_row.addWidget(self.text_model_combo)
        text_refresh = QPushButton("↻")
        text_refresh.setFixedWidth(28)
        text_refresh.setToolTip("Refresh model list")
        text_refresh.clicked.connect(lambda: self.populate_models())
        text_row.addWidget(text_refresh)

        vision_row = QHBoxLayout()
        vision_row.addWidget(self.vision_model_combo)
        vision_refresh = QPushButton("↻")
        vision_refresh.setFixedWidth(28)
        vision_refresh.setToolTip("Refresh model list")
        vision_refresh.clicked.connect(lambda: self.populate_models())
        vision_row.addWidget(vision_refresh)

        layout.addRow("Text model:", text_row)
        layout.addRow("Vision model:", vision_row)

        self.text_model_combo.currentTextChanged.connect(self._on_text_changed)
        self.vision_model_combo.currentTextChanged.connect(self._on_vision_changed)

        self.populate_models()

    # ── Population ─────────────────────────────────────────────────────────
    def populate_models(self, models: list[str] | None = None):
        if models is None:
            try:
                models = OllamaClient().list_models()
            except Exception:
                models = []

        self.text_model_combo.blockSignals(True)
        self.vision_model_combo.blockSignals(True)
        self.text_model_combo.clear()
        self.vision_model_combo.clear()

        if not models:
            self.text_model_combo.addItem(_NOT_RUNNING)
            self.vision_model_combo.addItem(_NOT_RUNNING)
            self.text_model_combo.blockSignals(False)
            self.vision_model_combo.blockSignals(False)
            return

        vision_models = [m for m in models
                         if any(h in m.lower() for h in _VISION_HINTS)]

        self.text_model_combo.addItems(models)
        self.vision_model_combo.addItems(vision_models or models)

        self._apply_default(self.text_model_combo, models,
                            self._settings.value("text_model"),
                            os.environ.get("TEXT_MODEL", "llama3.2:latest"),
                            prefer=("llama3.2", "coder", "vl:4b", "qwen"))
        self._apply_default(self.vision_model_combo,
                            vision_models or models,
                            self._settings.value("vision_model"),
                            os.environ.get("VISION_MODEL", "qwen3-vl:4b"),
                            prefer=("vl:4b", "vl", "llava"))

        self.text_model_combo.blockSignals(False)
        self.vision_model_combo.blockSignals(False)

    @staticmethod
    def _apply_default(combo: QComboBox, available: list[str],
                       saved, env_default: str, prefer: tuple):
        # Priority: .env default -> saved selection -> preference keyword -> first.
        # .env wins because it is calibrated for THIS machine's VRAM; otherwise a
        # stale oversized selection persisted in QSettings (e.g. from before a
        # hardware-aware fix) would keep getting loaded and could crash/freeze.
        for candidate in (env_default, saved):
            if candidate and candidate in available:
                combo.setCurrentText(candidate)
                return
        for kw in prefer:
            for m in available:
                if kw in m.lower():
                    combo.setCurrentText(m)
                    return
        if available:
            combo.setCurrentIndex(0)

    # ── Selection handlers ─────────────────────────────────────────────────
    def _on_text_changed(self, name: str):
        if name and name != _NOT_RUNNING:
            self._settings.setValue("text_model", name)
            self.text_model_changed.emit(name)

    def _on_vision_changed(self, name: str):
        if name and name != _NOT_RUNNING:
            self._settings.setValue("vision_model", name)
            self.vision_model_changed.emit(name)

    # ── Accessors ──────────────────────────────────────────────────────────
    def get_text_model(self) -> str:
        val = self.text_model_combo.currentText()
        return "" if val == _NOT_RUNNING else val

    def get_vision_model(self) -> str:
        val = self.vision_model_combo.currentText()
        return "" if val == _NOT_RUNNING else val
