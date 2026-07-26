"""Forge3D — input panel (text / image / PDF tabs)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.drop_zone import DropZone

_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]
_PDF_EXTS = [".pdf"]

_TEXT_PLACEHOLDER = (
    "Describe the 3D part you want to generate...\n\n"
    "Example: A flanged pipe connector 50mm diameter, 100mm long with\n"
    "four M6 bolt holes on the flange, equally spaced on a 70mm PCD"
)


class InputPanel(QWidget):
    """Three-tab input area plus the Generate button."""

    generate_requested = Signal(str, str, str)  # input_type, input_data, user_hint

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path: str | None = None
        self._pdf_path: str | None = None

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_text_tab()
        self._build_image_tab()
        self._build_pdf_tab()

        self.generate_btn = QPushButton("Generate STEP")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setShortcut("Ctrl+Return")
        self.generate_btn.setObjectName("generateButton")
        self.generate_btn.clicked.connect(self._on_generate)
        root.addWidget(self.generate_btn)

    # ── Tabs ───────────────────────────────────────────────────────────────
    def _build_text_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(_TEXT_PLACEHOLDER)
        self.text_edit.setMinimumHeight(150)
        layout.addWidget(self.text_edit)

        dims = QFormLayout()
        self.len_edit = QLineEdit()
        self.wid_edit = QLineEdit()
        self.hgt_edit = QLineEdit()
        for e, ph in ((self.len_edit, "optional"),
                      (self.wid_edit, "optional"),
                      (self.hgt_edit, "optional")):
            e.setPlaceholderText(ph)
        dims.addRow("Length (mm):", self.len_edit)
        dims.addRow("Width (mm):", self.wid_edit)
        dims.addRow("Height (mm):", self.hgt_edit)
        layout.addLayout(dims)

        self.tabs.addTab(tab, "Text")

    def _build_image_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.image_drop = DropZone(_IMAGE_EXTS, "Drop image here or click to browse")
        self.image_drop.file_loaded.connect(self._on_image_loaded)
        layout.addWidget(self.image_drop)

        self.image_hint = QLineEdit()
        self.image_hint.setPlaceholderText("Additional hints (optional)")
        layout.addWidget(self.image_hint)

        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMaximumHeight(140)
        layout.addWidget(self.image_preview)
        layout.addStretch(1)

        self.tabs.addTab(tab, "Image")

    def _build_pdf_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.pdf_drop = DropZone(_PDF_EXTS, "Drop PDF drawing here or click to browse")
        self.pdf_drop.file_loaded.connect(self._on_pdf_loaded)
        layout.addWidget(self.pdf_drop)

        self.pdf_info = QLabel("")
        layout.addWidget(self.pdf_info)

        self.pdf_use_vision = QCheckBox("Use vision model to analyse drawing layout")
        self.pdf_use_vision.setChecked(True)
        layout.addWidget(self.pdf_use_vision)
        layout.addStretch(1)

        self.tabs.addTab(tab, "PDF Drawing")

    # ── Loaders ────────────────────────────────────────────────────────────
    def _on_image_loaded(self, path: str):
        self._image_path = path
        pix = QPixmap(path)
        if not pix.isNull():
            self.image_preview.setPixmap(
                pix.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_pdf_loaded(self, path: str):
        self._pdf_path = path
        try:
            import fitz
            with fitz.open(path) as doc:
                self.pdf_info.setText(f"Loaded: {Path(path).name} ({doc.page_count} pages)")
        except Exception:
            self.pdf_info.setText(f"Loaded: {Path(path).name}")

    # ── Public API ─────────────────────────────────────────────────────────
    def get_current_input(self) -> tuple[str, str, str]:
        idx = self.tabs.currentIndex()
        if idx == 0:  # text
            prompt = self.text_edit.toPlainText().strip()
            extras = []
            for label, edit in (("length", self.len_edit),
                                ("width", self.wid_edit),
                                ("height", self.hgt_edit)):
                v = edit.text().strip()
                if v:
                    extras.append(f"{label} {v}mm")
            if extras:
                prompt = f"{prompt} ({', '.join(extras)})"
            if len(prompt) <= 10:
                raise ValueError("Please enter a longer description (>10 characters).")
            return "text", prompt, ""

        if idx == 1:  # image
            if not self._image_path:
                raise ValueError("Please load an image first.")
            return "image", self._image_path, self.image_hint.text().strip()

        if idx == 2:  # pdf
            if not self._pdf_path:
                raise ValueError("Please load a PDF drawing first.")
            hint = "" if self.pdf_use_vision.isChecked() else "text-only"
            return "pdf", self._pdf_path, hint

        raise ValueError("Unknown input tab.")

    def set_enabled(self, enabled: bool):
        self.tabs.setEnabled(enabled)
        self.generate_btn.setEnabled(enabled)

    # ── Internal ───────────────────────────────────────────────────────────
    def _on_generate(self):
        try:
            input_type, input_data, user_hint = self.get_current_input()
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.generate_requested.emit(input_type, input_data, user_hint)
