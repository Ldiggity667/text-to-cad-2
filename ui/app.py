"""Forge3D — QApplication factory and dark theme."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication


_DARK_QSS = """
QMainWindow, QDialog { background-color: #0d0d1a; }
QWidget { color: #e0e0ff; font-size: 13px; }

QLabel { color: #e0e0ff; background: transparent; }

QTabWidget::pane { border: 1px solid #2a2a4a; background: #1a1a2e; }
QTabBar::tab {
    background: #16213e; color: #888899;
    padding: 6px 14px; border: 1px solid #2a2a4a; border-bottom: none;
}
QTabBar::tab:selected { background: #1a1a2e; color: #e0e0ff; }
QTabBar::tab:hover { color: #e0e0ff; }

QPushButton {
    background-color: #16213e; color: #e0e0ff;
    border: 1px solid #2a2a4a; border-radius: 4px; padding: 6px 12px;
}
QPushButton:hover { background-color: #1f2b50; border-color: #7f77dd; }
QPushButton:pressed { background-color: #534ab7; }
QPushButton:disabled { color: #555566; background-color: #12121f; }

QPushButton#generateButton {
    background-color: #7f77dd; color: #ffffff; font-weight: bold;
    border: none; border-radius: 6px;
}
QPushButton#generateButton:hover { background-color: #6a62c8; }
QPushButton#generateButton:pressed { background-color: #534ab7; }
QPushButton#generateButton:disabled { background-color: #3a3760; color: #aaaacc; }

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: #16213e; color: #e0e0ff;
    border: 1px solid #2a2a4a; border-radius: 4px; padding: 4px;
    selection-background-color: #534ab7;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #7f77dd; }

QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background-color: #16213e; color: #e0e0ff;
    selection-background-color: #534ab7; border: 1px solid #2a2a4a;
}

QListWidget {
    background-color: #16213e; color: #e0e0ff;
    border: 1px solid #2a2a4a; border-radius: 4px;
}
QListWidget::item:selected { background-color: #534ab7; }
QListWidget::item:hover { background-color: #1f2b50; }

QCheckBox { color: #e0e0ff; }
QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid #2a2a4a;
    border-radius: 3px; background: #16213e;
}
QCheckBox::indicator:checked { background: #7f77dd; border-color: #7f77dd; }

QScrollBar:vertical { background: #0d0d1a; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #2a2a4a; border-radius: 6px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #534ab7; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: #0d0d1a; height: 12px; }
QScrollBar::handle:horizontal { background: #2a2a4a; border-radius: 6px; min-width: 24px; }

QSplitter::handle { background: #2a2a4a; }
QSplitter::handle:hover { background: #534ab7; }

QMenuBar { background-color: #0d0d1a; color: #e0e0ff; }
QMenuBar::item:selected { background: #1f2b50; }
QMenu { background-color: #16213e; color: #e0e0ff; border: 1px solid #2a2a4a; }
QMenu::item:selected { background: #534ab7; }

QToolBar { background: #12121f; border-bottom: 1px solid #2a2a4a; spacing: 6px; padding: 4px; }
QToolBar QToolButton { color: #e0e0ff; padding: 4px 8px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #1f2b50; }

QStatusBar { background: #12121f; color: #888899; }

QToolTip { background-color: #16213e; color: #e0e0ff; border: 1px solid #7f77dd; }
"""


def create_app() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("Forge3D")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Forge3D")
    app.setStyleSheet(_DARK_QSS)
    return app
