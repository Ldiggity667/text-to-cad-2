#!/usr/bin/env python
"""Run this to verify all Forge3D prerequisites are met."""

import sys
from pathlib import Path

CHECKS = []


def check(name, fn):
    try:
        result = fn()
        CHECKS.append((name, True, result or "OK"))
    except Exception as e:
        CHECKS.append((name, False, str(e)))


# Python version
check(
    "Python >= 3.11",
    lambda: f"Python {sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 11)
    else (_ for _ in ()).throw(Exception("Need Python 3.11+")),
)

check("build123d import", lambda: __import__("build123d") and "OK")
check("PySide6 import", lambda: __import__("PySide6.QtWidgets") and "OK")
check("PyMuPDF import", lambda: __import__("fitz") and "OK")
check("Pillow import", lambda: __import__("PIL.Image") and "OK")
check("requests import", lambda: __import__("requests") and "OK")


def check_ollama():
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=3)
    models = [m["name"] for m in r.json().get("models", [])]
    return f"Running. Models: {', '.join(models) or 'none installed'}"


check("Ollama running", check_ollama)

check(
    "outputs/ writable",
    lambda: Path("outputs").mkdir(exist_ok=True)
    or Path("outputs/test.tmp").write_text("ok")
    or Path("outputs/test.tmp").unlink()
    or "OK",
)

print("\n=== Forge3D Setup Verification ===\n")
all_ok = True
for name, ok, msg in CHECKS:
    icon = "[OK]" if ok else "[!!]"
    print(f"  {icon}  {name}: {msg}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("All checks passed. Ready to build Forge3D.")
else:
    print("Some checks failed. Fix the issues above before proceeding.")
    sys.exit(1)
