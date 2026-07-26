"""Forge3D — generation history panel."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_MAX_ITEMS = 50
_TYPE_BADGE = {"text": "T", "image": "I", "pdf": "P"}


@dataclass
class HistoryItem:
    step_path: Path
    input_type: str
    timestamp: datetime
    duration: float
    success: bool


class HistoryPanel(QWidget):
    """A reverse-chronological list of past generations."""

    step_selected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._output_dir = (Path(__file__).resolve().parents[2] / "outputs")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Generation history"))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget, 1)

        self.empty_label = QLabel("No generations yet")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #888899;")
        layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear history")
        clear_btn.clicked.connect(self.clear_history)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(open_btn)
        layout.addLayout(btn_row)

        self._refresh_empty_state()

    # ── Public API ─────────────────────────────────────────────────────────
    def add_result(self, result):
        """Add a GenerationResult at the top of the list."""
        ts = datetime.now()
        badge = _TYPE_BADGE.get(result.input_type, "?")
        mark = "✓" if result.success else "✗"
        name = result.step_path.name if result.step_path else "(no file)"
        if len(name) > 30:
            name = name[:27] + "..."
        text = (f"[{badge}] {name}   {ts.strftime('%H:%M:%S')}   "
                f"{result.duration_seconds:.1f}s   {mark}")

        item = QListWidgetItem(text)
        item.setForeground(Qt.green if result.success else Qt.red)
        if result.success and result.step_path:
            item.setData(Qt.UserRole, str(result.step_path))
        self.list_widget.insertItem(0, item)

        while self.list_widget.count() > _MAX_ITEMS:
            self.list_widget.takeItem(self.list_widget.count() - 1)

        self._refresh_empty_state()

    def clear_history(self):
        if self.list_widget.count() == 0:
            return
        resp = QMessageBox.question(
            self, "Clear history", "Clear the generation history list?")
        if resp == QMessageBox.Yes:
            self.list_widget.clear()
            self._refresh_empty_state()

    # ── Internal ───────────────────────────────────────────────────────────
    def _on_double_click(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self.step_selected.emit(Path(path))

    def _open_folder(self):
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(self._output_dir))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(self._output_dir)])
        else:
            subprocess.run(["xdg-open", str(self._output_dir)])

    def _refresh_empty_state(self):
        empty = self.list_widget.count() == 0
        self.empty_label.setVisible(empty)
        self.list_widget.setVisible(not empty)
