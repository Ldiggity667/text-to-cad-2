"""Forge3D launcher.

A tiny bootstrap compiled to Forge3D.exe. It does NOT bundle the heavy CAD
stack — it simply starts the real app using the project's virtual environment,
so build123d / OCP and the subprocess code-runner keep working normally.
"""

import subprocess
import sys
from pathlib import Path

# Fixed install location of the Forge3D project.
ROOT = Path(r"C:\CAD_Automation\Forge3D")


def _error(msg: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Forge3D", 0x10)
    except Exception:
        print(msg)


def main() -> None:
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    exe = pythonw if pythonw.exists() else python
    main_py = ROOT / "main.py"

    if not exe.exists():
        _error(f"Could not find the Forge3D virtual environment at:\n{exe}\n\n"
               f"Reinstall or recreate the .venv.")
        return
    if not main_py.exists():
        _error(f"Could not find main.py at:\n{main_py}")
        return

    # Launch detached so the launcher process can exit immediately.
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = 0x00000008  # DETACHED_PROCESS
    subprocess.Popen([str(exe), str(main_py)], cwd=str(ROOT),
                     creationflags=creationflags, close_fds=True)


if __name__ == "__main__":
    main()
