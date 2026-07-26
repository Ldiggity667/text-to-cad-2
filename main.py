import sys
from pathlib import Path

# Add project root to Python path.
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from PySide6.QtCore import QTimer

from ui.app import create_app
from ui.main_window import MainWindow


def main():
    app = create_app()
    window = MainWindow()
    window.show()

    # Non-blocking startup checks shortly after the window appears.
    QTimer.singleShot(1000, window._check_ollama_startup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
