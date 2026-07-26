"""Forge3D — colour-coded log console."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import QTextEdit


_COLORS = {
    "info": "#888888",
    "warning": "#f0a500",
    "success": "#00c853",
    "error": "#ff5252",
    "stream": "#7090b0",
}

_MAX_LINES = 1000


class LogConsole(QTextEdit):
    """Read-only console that colour-codes log levels and auto-scrolls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setMaximumHeight(180)
        self.setStyleSheet(
            "background-color: #0d0d1a; color: #cccccc; border: 1px solid #333;"
        )

    def append_log(self, level: str, message: str):
        color = _COLORS.get(level, "#cccccc")
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if level == "stream":
            # Stream tokens are appended inline (no timestamp, no newline).
            html = f'<span style="color:{color};">{_escape(message)}</span>'
            cursor.insertHtml(html)
        else:
            ts = datetime.now().strftime("%H:%M:%S")
            html = (f'<span style="color:#555;">{ts}</span> '
                    f'<span style="color:{color};">{_escape(message)}</span><br>')
            cursor.insertHtml(html)

        self._trim()
        self._scroll_to_bottom()

    def clear_log(self):
        self.clear()

    # ── Internal ───────────────────────────────────────────────────────────
    def _scroll_to_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _trim(self):
        doc = self.document()
        if doc.blockCount() <= _MAX_LINES:
            return
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.Start)
        excess = doc.blockCount() - _MAX_LINES
        for _ in range(excess):
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the leftover newline


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>"))
