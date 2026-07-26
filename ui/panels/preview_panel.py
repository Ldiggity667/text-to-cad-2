"""Forge3D — 3D preview panel (QWebEngineView hosting the Three.js viewer)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

_VIEWER_HTML = Path(__file__).resolve().parents[1] / "viewer" / "index.html"
_LARGE_FILE_BYTES = 50 * 1024 * 1024   # 50 MB


class PreviewPanel(QWidget):
    """Embeds the WebGL STEP viewer and a small camera/render toolbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page_ready = False
        self._dark_bg = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QToolBar()
        toolbar.addAction("Fit to view", self._fit)
        toolbar.addAction("Reset camera", self._reset)
        toolbar.addAction("Wireframe", self._wireframe)
        toolbar.addAction("Dark/Light bg", self._toggle_bg)
        layout.addWidget(toolbar)

        self.view = QWebEngineView()
        # Allow the local file:// viewer page to load its vendored JS/WASM.
        settings = self.view.settings()
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.view.page().loadFinished.connect(self._on_page_loaded)
        self.view.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))
        layout.addWidget(self.view, 1)

    # ── Public API ─────────────────────────────────────────────────────────
    def load_step(self, step_path: Path):
        step_path = Path(step_path)
        if not step_path.exists():
            QMessageBox.warning(self, "Preview", "STEP file not found.")
            return

        size = step_path.stat().st_size
        if size == 0:
            self._run_js('window.setStatus("Empty STEP file — generation may have failed")')
            return
        if size > _LARGE_FILE_BYTES:
            resp = QMessageBox.question(
                self, "Large file",
                f"This STEP file is {size // (1024*1024)} MB and may load slowly. "
                "Continue?")
            if resp != QMessageBox.Yes:
                return

        content = step_path.read_text(encoding="utf-8", errors="replace")
        escaped = (content.replace("\\", "\\\\")
                          .replace("`", "\\`")
                          .replace("$", "\\$"))
        self._run_js(f"window.loadStep(`{escaped}`)")

    def clear(self):
        self._run_js("window.clearScene()")

    def set_status(self, message: str):
        safe = message.replace("\\", "\\\\").replace('"', '\\"')
        self._run_js(f'window.setStatus("{safe}")')

    # ── Toolbar actions ────────────────────────────────────────────────────
    def _fit(self):
        self._run_js("window.fitToView()")

    def _reset(self):
        self._run_js("window.resetCamera()")

    def _wireframe(self):
        self._run_js("window.toggleWireframe()")

    def _toggle_bg(self):
        self._dark_bg = not self._dark_bg
        self._run_js(f"window.setBackground({'true' if self._dark_bg else 'false'})")

    # ── Internal ───────────────────────────────────────────────────────────
    def _on_page_loaded(self, ok: bool):
        self._page_ready = ok
        if ok:
            self.set_status("3D viewer ready")
        else:
            QMessageBox.warning(self, "Preview", "Failed to load the 3D viewer.")

    def _run_js(self, script: str):
        self.view.page().runJavaScript(script)
