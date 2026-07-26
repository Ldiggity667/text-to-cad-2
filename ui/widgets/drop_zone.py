"""Forge3D — drag-and-drop / click-to-browse file zone."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QWidget


class DropZone(QWidget):
    """A bordered area that accepts a file via drag-drop or click-to-browse."""

    file_loaded = Signal(str)   # emits the file path

    def __init__(self, accepted_extensions: list[str], placeholder_text: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.accepted_extensions = [e.lower() for e in accepted_extensions]
        self.placeholder_text = placeholder_text
        self.current_file: str | None = None
        self._hover = False

        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setCursor(Qt.PointingHandCursor)

    # ── Public API ─────────────────────────────────────────────────────────
    def clear(self):
        self.current_file = None
        self.update()

    # ── Helpers ────────────────────────────────────────────────────────────
    def _matches(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.accepted_extensions

    def _filter_string(self) -> str:
        pats = " ".join(f"*{e}" for e in self.accepted_extensions)
        return f"Accepted files ({pats})"

    def _set_file(self, path: str):
        self.current_file = path
        self.update()
        self.file_loaded.emit(path)

    # ── Drag & drop ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile() and self._matches(url.toLocalFile()):
                    self._hover = True
                    self.update()
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._hover = False
        self.update()

    def dropEvent(self, event):
        self._hover = False
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if self._matches(path):
                    self._set_file(path)
                    event.acceptProposedAction()
                    self.update()
                    return
        self.update()
        event.ignore()

    # ── Click to browse ────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select file", "", self._filter_string())
            if path and self._matches(path):
                self._set_file(path)

    # ── Painting ───────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        border_color = QColor("#7f77dd") if self._hover else QColor("#555")
        pen = QPen(border_color, 2, Qt.DashLine)
        painter.setPen(pen)
        if self._hover:
            painter.setBrush(QColor(127, 119, 221, 25))
        painter.drawRoundedRect(rect, 8, 8)

        painter.setPen(QColor("#cccccc"))
        if self.current_file:
            name = Path(self.current_file).name
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, f"\U0001F4C4  {name}")
        else:
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QColor("#888899"))
            painter.drawText(rect, Qt.AlignCenter, self.placeholder_text)

        painter.end()
