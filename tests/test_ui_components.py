"""Standalone smoke test for the Forge3D UI widgets.

Run:  python test_ui_components.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from ui.widgets.log_console import LogConsole
from ui.widgets.drop_zone import DropZone

app = QApplication(sys.argv)
window = QMainWindow()
central = QWidget()
layout = QVBoxLayout(central)

console = LogConsole()
console.append_log("info", "Application started")
console.append_log("success", "Build123d loaded")
console.append_log("warning", "Vision model not found")
console.append_log("error", "Connection refused")
layout.addWidget(console)

dropzone = DropZone([".step", ".stp"], "Drop STEP file here")
layout.addWidget(dropzone)

window.setCentralWidget(central)
window.resize(600, 400)
window.show()
sys.exit(app.exec())
