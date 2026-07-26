"""Forge3D — settings dialog."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import APP_VERSION
from core.ollama_client import OllamaClient

_VISION_HINTS = ("llava", "vision", "vl", "gemma3", "bakllava", "moondream")


class SettingsDialog(QDialog):
    """Persistent app settings (Ollama, models, output) stored via QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Forge3D", "Forge3D")

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setFixedSize(480, 420)

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_ollama_tab()
        self._build_models_tab()
        self._build_output_tab()
        self._build_about_tab()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._load_settings()

    # ── Tabs ───────────────────────────────────────────────────────────────
    def _build_ollama_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.host_edit = QLineEdit()
        form.addRow("Host URL:", self.host_edit)

        test_btn = QPushButton("Test Connection")
        self.test_status = QLabel("")
        test_btn.clicked.connect(self._test_connection)
        test_row = QHBoxLayout()
        test_row.addWidget(test_btn)
        test_row.addWidget(self.test_status, 1)
        form.addRow("", self._wrap(test_row))

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 5)
        form.addRow("Max retries:", self.retries_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 300)
        self.timeout_spin.setSuffix(" s")
        form.addRow("Code timeout:", self.timeout_spin)

        self.tabs.addTab(tab, "Ollama")

    def _build_models_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.text_combo = QComboBox()
        self.vision_combo = QComboBox()
        form.addRow("Text model:", self.text_combo)
        form.addRow("Vision model:", self.vision_combo)

        refresh = QPushButton("Refresh models")
        refresh.clicked.connect(self._refresh_models)
        form.addRow("", refresh)

        self.model_info = QLabel("")
        self.model_info.setWordWrap(True)
        form.addRow("Info:", self.model_info)

        self.tabs.addTab(tab, "Models")
        self._refresh_models()

    def _build_output_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.output_edit = QLineEdit()
        out_browse = QPushButton("Browse")
        out_browse.clicked.connect(lambda: self._browse(self.output_edit))
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(out_browse)
        form.addRow("Output directory:", self._wrap(out_row))

        self.temp_edit = QLineEdit()
        temp_browse = QPushButton("Browse")
        temp_browse.clicked.connect(lambda: self._browse(self.temp_edit))
        temp_row = QHBoxLayout()
        temp_row.addWidget(self.temp_edit, 1)
        temp_row.addWidget(temp_browse)
        form.addRow("Temp directory:", self._wrap(temp_row))

        self.auto_open = QCheckBox("Auto-open STEP file after generation")
        self.keep_temp = QCheckBox("Keep temp scripts for debugging")
        self.write_meta = QCheckBox("Write metadata .json alongside STEP")
        self.write_meta.setChecked(True)
        form.addRow(self.auto_open)
        form.addRow(self.keep_temp)
        form.addRow(self.write_meta)

        self.tabs.addTab(tab, "Output")

    def _build_about_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"Forge3D {APP_VERSION}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        for text in (
            "Built with build123d, Ollama, PySide6, Three.js",
            "Offline-first. No telemetry. No cloud.",
        ):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

        links = QLabel(
            '<a href="https://build123d.readthedocs.io">build123d docs</a> &nbsp;|&nbsp; '
            '<a href="https://github.com/ollama/ollama">Ollama docs</a>')
        links.setAlignment(Qt.AlignCenter)
        links.setOpenExternalLinks(True)
        layout.addWidget(links)

        self.tabs.addTab(tab, "About")

    # ── Behaviour ──────────────────────────────────────────────────────────
    def _test_connection(self):
        host = self.host_edit.text().strip() or None
        if OllamaClient(host).is_available():
            self.test_status.setText("✓ Connected")
            self.test_status.setStyleSheet("color: #00c853;")
        else:
            self.test_status.setText("✗ Not reachable")
            self.test_status.setStyleSheet("color: #ff5252;")

    def _refresh_models(self):
        host = self.host_edit.text().strip() or None
        try:
            models = OllamaClient(host).list_models()
        except Exception:
            models = []
        cur_text = self.text_combo.currentText()
        cur_vision = self.vision_combo.currentText()
        self.text_combo.clear()
        self.vision_combo.clear()
        if models:
            self.text_combo.addItems(models)
            vision = [m for m in models
                      if any(h in m.lower() for h in _VISION_HINTS)]
            self.vision_combo.addItems(vision or models)
            self.model_info.setText(f"{len(models)} models available.")
        else:
            self.model_info.setText("Ollama not running or no models installed.")
        if cur_text:
            self.text_combo.setCurrentText(cur_text)
        if cur_vision:
            self.vision_combo.setCurrentText(cur_vision)

    def _browse(self, target: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Select directory",
                                             target.text() or ".")
        if d:
            target.setText(d)

    def _wrap(self, layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    # ── Persistence ────────────────────────────────────────────────────────
    def _load_settings(self):
        s = self._settings
        self.host_edit.setText(
            s.value("ollama_host",
                    os.environ.get("OLLAMA_HOST", "http://localhost:11434")))
        self.retries_spin.setValue(int(s.value("max_retries", 3)))
        self.timeout_spin.setValue(int(s.value("code_timeout", 120)))

        root = Path(__file__).resolve().parents[2]
        self.output_edit.setText(s.value("output_dir", str(root / "outputs")))
        self.temp_edit.setText(s.value("temp_dir", str(root / "temp")))
        self.auto_open.setChecked(s.value("auto_open", False, type=bool))
        self.keep_temp.setChecked(s.value("keep_temp", False, type=bool))
        self.write_meta.setChecked(s.value("write_metadata", True, type=bool))

        text_model = s.value("text_model")
        vision_model = s.value("vision_model")
        if text_model:
            self.text_combo.setCurrentText(text_model)
        if vision_model:
            self.vision_combo.setCurrentText(vision_model)

    def _save_and_accept(self):
        s = self._settings
        s.setValue("ollama_host", self.host_edit.text().strip())
        s.setValue("max_retries", self.retries_spin.value())
        s.setValue("code_timeout", self.timeout_spin.value())
        s.setValue("output_dir", self.output_edit.text().strip())
        s.setValue("temp_dir", self.temp_edit.text().strip())
        s.setValue("auto_open", self.auto_open.isChecked())
        s.setValue("keep_temp", self.keep_temp.isChecked())
        s.setValue("write_metadata", self.write_meta.isChecked())
        if self.text_combo.currentText():
            s.setValue("text_model", self.text_combo.currentText())
        if self.vision_combo.currentText():
            s.setValue("vision_model", self.vision_combo.currentText())
        self.accept()
