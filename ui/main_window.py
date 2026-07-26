"""Forge3D — main window and background generation worker."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core import APP_VERSION
from core.ollama_client import OllamaClient
from core.pipeline import Pipeline
from ui.panels.history_panel import HistoryPanel
from ui.panels.input_panel import InputPanel
from ui.panels.preview_panel import PreviewPanel
from ui.widgets.log_console import LogConsole
from ui.widgets.model_selector import ModelSelector


def detect_vram_mb() -> int | None:
    """Best-effort total GPU VRAM in MB. Override with FORGE3D_VRAM_GB env var.
    Returns None if it cannot be determined."""
    import os
    import subprocess

    env = os.environ.get("FORGE3D_VRAM_GB")
    if env:
        try:
            return int(float(env) * 1024)
        except ValueError:
            pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return int(out.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None
    return None


# ── Background worker ───────────────────────────────────────────────────────
class GenerationWorker(QObject):
    """Runs Pipeline.generate() off the main thread."""

    log_message = Signal(str, str)      # level, message
    code_ready = Signal(str)            # generated code
    generation_done = Signal(object)    # GenerationResult
    error_occurred = Signal(str)        # error message

    def __init__(self, input_type, input_data, user_hint,
                 text_model, vision_model):
        super().__init__()
        self.input_type = input_type
        self.input_data = input_data
        self.user_hint = user_hint
        self.text_model = text_model
        self.vision_model = vision_model

    def run(self):
        try:
            pipeline = Pipeline()
            result = pipeline.generate(
                input_type=self.input_type,
                input_data=self.input_data,
                user_hint=self.user_hint,
                model_text=self.text_model or None,
                model_vision=self.vision_model or None,
                on_log=lambda level, msg: self.log_message.emit(level, msg),
                on_code_ready=lambda code: self.code_ready.emit(code),
            )
            self.generation_done.emit(result)
        except Exception as e:  # never let the thread die silently
            self.error_occurred.emit(str(e))


# ── Main window ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._settings = QSettings("Forge3D", "Forge3D")
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None
        self._busy = False
        self._cancelled = False
        self._gen_start = 0.0
        self._last_step_path: Path | None = None

        self.setWindowTitle("Forge3D — AI-powered 3D Generator")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self._build_widgets()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._build_layout()
        self._connect_signals()
        self._restore_geometry()
        self._apply_settings_to_env()

        # Generation timer for the status bar.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_timer)

    # ── Construction ───────────────────────────────────────────────────────
    def _build_widgets(self):
        self.input_panel = InputPanel()
        self.log_console = LogConsole()
        self.preview_panel = PreviewPanel()
        self.history_panel = HistoryPanel()
        self.model_selector = ModelSelector()

    def _build_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._act("New Session", self._new_session))
        file_menu.addAction(self._act("Open STEP...", self._open_step))
        file_menu.addAction(self._act("Export STEP...", self._export_step, "Ctrl+S"))
        file_menu.addSeparator()
        file_menu.addAction(self._act("Exit", self.close))

        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._act("Toggle History Panel",
                                      self._toggle_history, "Ctrl+H"))
        view_menu.addAction(self._act("Toggle Log Console",
                                      self._toggle_log, "Ctrl+`"))
        view_menu.addSeparator()
        view_menu.addAction(self._act("Fullscreen", self._toggle_fullscreen, "F11"))

        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self._act("Settings...", self._open_settings, "Ctrl+,"))
        tools_menu.addAction(self._act("Check Ollama", self._check_ollama))
        tools_menu.addSeparator()
        tools_menu.addAction(self._act("Open Output Folder",
                                       self.history_panel._open_folder))

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._act("About", self._about))
        help_menu.addAction(self._act("Keyboard Shortcuts", self._shortcuts_help))

        # Extra shortcuts not on a visible button.
        self.addAction(self._act("Clear log", self.log_console.clear_log, "Ctrl+L"))
        self.addAction(self._act("Cancel", self._cancel_generation, "Escape"))

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.generate_action = self._act("Generate STEP",
                                         self._on_generate_clicked, "Ctrl+Return")
        tb.addAction(self.generate_action)
        self.stop_action = self._act("Stop", self._cancel_generation)
        self.stop_action.setEnabled(False)
        tb.addAction(self.stop_action)
        tb.addAction(self._act("Export", self._export_step))
        tb.addAction(self._act("Open Output Folder",
                               self.history_panel._open_folder))

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(),
                             spacer.sizePolicy().verticalPolicy())
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(self.model_selector)

    def _build_statusbar(self):
        sb = self.statusBar()
        self.status_label = QLabel("Ready")
        self.model_label = QLabel("")
        self.timer_label = QLabel("")
        sb.addWidget(self.status_label, 1)
        sb.addPermanentWidget(self.model_label)
        sb.addPermanentWidget(self.timer_label)
        self._update_model_label()

    def _build_layout(self):
        # Left panel: input + collapsible log console.
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(self.input_panel, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2a2a4a;")
        left_layout.addWidget(sep)

        self.log_toggle_btn = QPushButton("▸ Log console")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.clicked.connect(self._toggle_log)
        left_layout.addWidget(self.log_toggle_btn)
        self.log_console.setVisible(False)
        left_layout.addWidget(self.log_console)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.addWidget(self.history_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([380, 760, 260])

        self.setCentralWidget(self.splitter)

    def _connect_signals(self):
        self.input_panel.generate_requested.connect(self._start_generation)
        self.history_panel.step_selected.connect(self.preview_panel.load_step)
        self.model_selector.text_model_changed.connect(
            lambda _: self._update_model_label())
        self.model_selector.vision_model_changed.connect(
            lambda _: self._update_model_label())

    # ── Generation flow ────────────────────────────────────────────────────
    def _on_generate_clicked(self):
        try:
            input_type, input_data, user_hint = self.input_panel.get_current_input()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self._start_generation(input_type, input_data, user_hint)

    def _start_generation(self, input_type: str, input_data: str, user_hint: str):
        if self._busy:
            QMessageBox.information(self, "Busy",
                                    "Generation in progress. Please wait.")
            return

        if not OllamaClient().is_available():
            self.log_console.setVisible(True)
            self.log_toggle_btn.setChecked(True)
            self.log_console.append_log(
                "error", "Ollama is not reachable. Start it with: ollama serve")
            QMessageBox.warning(
                self, "Ollama not running",
                "Cannot reach Ollama. Start it with:  ollama serve")
            return

        self._busy = True
        self._cancelled = False
        self.input_panel.set_enabled(False)
        self.generate_action.setEnabled(False)
        self.stop_action.setEnabled(True)
        self.log_console.clear_log()
        self.log_console.setVisible(True)
        self.log_toggle_btn.setChecked(True)
        self.preview_panel.set_status("Generating...")
        self.status_label.setText("Generating...")
        self._warn_if_model_oversized(input_type)
        self._gen_start = time.time()
        self._timer.start()

        self._worker = GenerationWorker(
            input_type, input_data, user_hint,
            self.model_selector.get_text_model(),
            self.model_selector.get_vision_model(),
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._worker.log_message.connect(self.log_console.append_log)
        self._worker.code_ready.connect(
            lambda code: self.log_console.append_log(
                "info", f"Generated {len(code)} chars of code."))
        self._worker.generation_done.connect(self._on_generation_done)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._thread.started.connect(self._worker.run)
        # Tell the thread to quit once work is done...
        self._worker.generation_done.connect(self._thread.quit)
        self._worker.error_occurred.connect(self._thread.quit)
        # ...then clean up only after the thread has fully finished. deleteLater
        # defers destruction to the event loop so the QThread is never destroyed
        # while still running.
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)

        self._thread.start()

    def _on_generation_done(self, result):
        self._finish_generation()

        self.history_panel.add_result(result)

        if self._cancelled:
            self.status_label.setText("Generation cancelled")
            self.log_console.append_log("warning", "Generation cancelled by user.")
            return

        if result.success:
            self._last_step_path = result.step_path
            self.preview_panel.load_step(result.step_path)
            self.status_label.setText(
                f"Generated in {result.duration_seconds}s "
                f"({result.attempts} attempt(s))")
            self.log_console.append_log(
                "success", f"Done: {result.step_path.name}")
            if self._settings.value("auto_open", False, type=bool):
                try:
                    import os
                    os.startfile(str(result.step_path))  # noqa: S606
                except Exception:
                    pass
        else:
            self.status_label.setText("Generation failed")
            self.log_console.append_log("error", result.error_message or "Failed.")
            QMessageBox.warning(self, "Generation failed",
                                result.error_message or "Unknown error.")

    def _on_worker_error(self, message: str):
        self._finish_generation()
        self.status_label.setText("Generation failed")
        self.log_console.append_log("error", message)
        QMessageBox.critical(self, "Error", message)

    def _finish_generation(self):
        # UI reset only — runs as soon as the result arrives. Thread teardown is
        # handled separately in _on_thread_finished (after thread.quit -> finished).
        self._timer.stop()
        self.timer_label.setText("")
        self._busy = False
        self.input_panel.set_enabled(True)
        self.generate_action.setEnabled(True)
        self.stop_action.setEnabled(False)

    def _on_thread_finished(self):
        # The QThread has stopped; drop our Python references. The Qt objects
        # are freed via deleteLater connected above.
        self._thread = None
        self._worker = None

    def _warn_if_model_oversized(self, input_type: str):
        """Non-blocking warning if the chosen model is too big for the GPU VRAM."""
        vram_mb = detect_vram_mb()
        if not vram_mb:
            return
        if input_type in ("image", "pdf"):
            model = self.model_selector.get_vision_model()
        else:
            model = self.model_selector.get_text_model()
        if not model:
            return
        size_b = OllamaClient().model_sizes().get(model)
        if not size_b:
            return
        size_mb = size_b / (1024 * 1024)
        if size_mb > vram_mb * 0.92:
            self.log_console.append_log(
                "warning",
                f"Model '{model}' is ~{size_mb / 1024:.1f} GB but this GPU has "
                f"~{vram_mb / 1024:.1f} GB VRAM. It will spill into system RAM and "
                f"may run very slowly or freeze. Pick a smaller model "
                f"(e.g. qwen3-vl:4b) in the toolbar.")

    def _cancel_generation(self):
        if not self._busy:
            return
        self._cancelled = True
        self.log_console.append_log(
            "warning", "Cancel requested — will stop after the current step.")
        self.stop_action.setEnabled(False)

    def _tick_timer(self):
        elapsed = int(time.time() - self._gen_start)
        self.timer_label.setText(f"{elapsed}s")

    # ── Menu / toolbar actions ─────────────────────────────────────────────
    def _new_session(self):
        if self._busy:
            return
        self.input_panel.text_edit.clear()
        self.input_panel.image_drop.clear()
        self.input_panel.pdf_drop.clear()
        self.preview_panel.clear()
        self.log_console.clear_log()
        self.status_label.setText("Ready")

    def _open_step(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open STEP file", "", "STEP Files (*.step *.stp)")
        if path:
            self._last_step_path = Path(path)
            self.preview_panel.load_step(Path(path))

    def _export_step(self):
        if not self._last_step_path or not self._last_step_path.exists():
            QMessageBox.information(self, "Export",
                                    "No generated STEP file to export yet.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export STEP", self._last_step_path.name,
            "STEP Files (*.step *.stp)")
        if dest:
            shutil.copy(self._last_step_path, dest)
            QMessageBox.information(self, "Export", f"Exported to {dest}")

    def _check_ollama(self):
        client = OllamaClient()
        if client.is_available():
            models = client.list_models()
            QMessageBox.information(
                self, "Ollama",
                "Ollama is running.\n\nInstalled models:\n" +
                "\n".join(f"  • {m}" for m in models))
        else:
            QMessageBox.warning(
                self, "Ollama",
                "Ollama is not reachable.\n\nStart it with:  ollama serve\n"
                "Or install from https://ollama.com")

    def _open_settings(self):
        from ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._apply_settings_to_env()
            self.model_selector.populate_models()
            self._update_model_label()

    def _apply_settings_to_env(self):
        """Push persisted settings into the environment so the pipeline picks
        them up on the next generation (keeps core decoupled from Qt)."""
        import os
        s = self._settings
        mapping = {
            "OLLAMA_HOST": s.value("ollama_host"),
            "MAX_RETRIES": s.value("max_retries"),
            "CODE_TIMEOUT_SECONDS": s.value("code_timeout"),
            "OUTPUT_DIR": s.value("output_dir"),
            "TEMP_DIR": s.value("temp_dir"),
        }
        for key, val in mapping.items():
            if val:
                os.environ[key] = str(val)
        os.environ["FORGE3D_KEEP_TEMP"] = (
            "1" if s.value("keep_temp", False, type=bool) else "0")

    def _toggle_history(self):
        self.history_panel.setVisible(not self.history_panel.isVisible())

    def _toggle_log(self):
        visible = not self.log_console.isVisible()
        self.log_console.setVisible(visible)
        self.log_toggle_btn.setChecked(visible)
        self.log_toggle_btn.setText(("▾ " if visible else "▸ ") + "Log console")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _about(self):
        QMessageBox.about(
            self, "About Forge3D",
            f"<h3>Forge3D {APP_VERSION}</h3>"
            "<p>AI-powered 3D STEP generator.</p>"
            "<p>Built with build123d, Ollama, PySide6, and Three.js.</p>"
            "<p><i>Offline-first. No telemetry. No cloud.</i></p>")

    def _shortcuts_help(self):
        QMessageBox.information(
            self, "Keyboard Shortcuts",
            "Ctrl+Enter — Generate STEP\n"
            "Ctrl+S — Export STEP\n"
            "Ctrl+L — Clear log console\n"
            "Ctrl+H — Toggle history panel\n"
            "Ctrl+, — Settings\n"
            "Escape — Cancel generation\n"
            "F11 — Fullscreen")

    # ── Startup check ──────────────────────────────────────────────────────
    def _check_ollama_startup(self):
        """Silent startup checks; report into the log console (non-blocking)."""
        self.log_console.setVisible(True)
        self.log_toggle_btn.setChecked(True)
        self.log_toggle_btn.setText("▾ Log console")
        log = self.log_console.append_log

        # 1. build123d importable.
        try:
            import build123d  # noqa: F401
            log("success", "build123d is available.")
        except ImportError:
            log("error", "build123d not importable — CAD generation will fail.")

        # 2. Output dir writable.
        try:
            out = Path(__file__).resolve().parents[1] / "outputs"
            out.mkdir(parents=True, exist_ok=True)
            test = out / ".write_test"
            test.write_text("ok")
            test.unlink()
            log("success", "Output directory is writable.")
        except Exception as e:
            log("warning", f"Output directory not writable: {e}")

        # 3. Ollama + required models.
        client = OllamaClient()
        if not client.is_available():
            log("warning",
                "Ollama not detected. Start with: ollama serve "
                "(or install from https://ollama.com)")
            self._show_ollama_banner()
            return

        models = client.list_models()
        log("success", f"Ollama running ({len(models)} models).")
        for kind, model in (("Text", self.model_selector.get_text_model()),
                            ("Vision", self.model_selector.get_vision_model())):
            if model and model in models:
                log("success", f"{kind} model '{model}' is available.")
            elif model:
                log("warning",
                    f"{kind} model '{model}' not installed. "
                    f"Pull it with: ollama pull {model}")

    def _show_ollama_banner(self):
        bar = self.statusBar()
        self.status_label.setText(
            "Ollama not detected — start with: ollama serve")

    # ── Helpers ────────────────────────────────────────────────────────────
    def _update_model_label(self):
        t = self.model_selector.get_text_model() or "?"
        v = self.model_selector.get_vision_model() or "?"
        self.model_label.setText(f"text: {t}  |  vision: {v}")

    def _act(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _restore_geometry(self):
        geo = self._settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)

    # ── Close ──────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self._busy:
            resp = QMessageBox.question(
                self, "Exit",
                "A generation is in progress. Exit anyway?")
            if resp != QMessageBox.Yes:
                event.ignore()
                return
            self._cancelled = True
            if self._thread:
                self._thread.quit()
                self._thread.wait(2000)
        self._settings.setValue("window_geometry", self.saveGeometry())
        event.accept()
