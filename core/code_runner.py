"""Forge3D — safe code runner.

Executes LLM-generated build123d scripts in an isolated subprocess (never
exec/eval, never in-process). One attempt per call; the pipeline drives retries.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class RunResult:
    success: bool
    step_path: Path | None           # path to generated STEP file, or None
    error_message: str | None        # human-readable error, or None
    raw_stderr: str | None           # raw subprocess stderr for retry prompts
    code_executed: str               # the Python code that was run
    attempt_number: int              # which attempt this result is for (1-based)
    execution_time_seconds: float


# Marker line the prompt engineer instructs the model to emit.
_OUTPUT_MARKER = 'OUTPUT_PATH = Path(__file__).parent / "output.step"'


class CodeRunner:
    """Runs a single build123d script in the project venv via subprocess."""

    def __init__(
        self,
        python_executable: str | None = None,
        output_dir: Path | None = None,
        temp_dir: Path | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ):
        root = Path(__file__).resolve().parents[1]
        self.python_executable = (
            Path(python_executable) if python_executable
            else self._find_python_executable()
        )
        # Defaults fall back to .env / environment so the Settings dialog can
        # influence behaviour without coupling this module to Qt. Relative dirs
        # (e.g. ./temp from .env) are resolved against the project root so the
        # subprocess cwd does not double-nest them.
        output_dir = output_dir or os.environ.get("OUTPUT_DIR")
        temp_dir = temp_dir or os.environ.get("TEMP_DIR")
        self.output_dir = self._resolve_dir(output_dir, root / "outputs", root)
        self.temp_dir = self._resolve_dir(temp_dir, root / "temp", root)
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None
            else _env_int("CODE_TIMEOUT_SECONDS", 120))
        self.max_retries = (
            max_retries if max_retries is not None
            else _env_int("MAX_RETRIES", 3))
        self.keep_temp = os.environ.get("FORGE3D_KEEP_TEMP", "0") == "1"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_dir(value, default: Path, root: Path) -> Path:
        if not value:
            return default
        p = Path(value).expanduser()
        return p if p.is_absolute() else (root / p).resolve()

    def _find_python_executable(self) -> Path:
        root = Path(__file__).resolve().parents[1]
        candidates = [
            root / ".venv" / "bin" / "python",            # Linux/macOS
            root / ".venv" / "Scripts" / "python.exe",    # Windows
        ]
        for c in candidates:
            if c.exists():
                return c
        return Path(sys.executable)  # fallback: current interpreter

    def run(
        self,
        code: str,
        output_filename: str | None = None,
        on_attempt: Callable[[int, str], None] | None = None,
    ) -> RunResult:
        """Execute `code` once, writing a STEP file to the output directory."""
        if output_filename is None:
            output_filename = f"forge3d_{uuid.uuid4().hex[:8]}.step"
        output_path = self.output_dir / output_filename

        attempt = 1
        start = time.time()

        # Inject the real output path in place of the marker, or prepend it.
        forced = f'OUTPUT_PATH = Path(r"{output_path}")'
        if _OUTPUT_MARKER in code:
            injected_code = code.replace(_OUTPUT_MARKER, forced)
        else:
            injected_code = f"{forced}\n{code}"

        # Stale-file guard: a STEP left from a prior run must not look like success.
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass

        temp_script = self.temp_dir / f"forge3d_run_{uuid.uuid4().hex[:8]}.py"
        temp_script.write_text(injected_code, encoding="utf-8")

        if on_attempt:
            on_attempt(attempt, injected_code)

        try:
            result = subprocess.run(
                [str(self.python_executable), str(temp_script)],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=str(self.temp_dir),
            )
        except subprocess.TimeoutExpired:
            self._cleanup(temp_script)
            return RunResult(
                success=False,
                step_path=None,
                error_message=(
                    f"Code execution timed out after {self.timeout_seconds}s."
                ),
                raw_stderr=None,
                code_executed=injected_code,
                attempt_number=attempt,
                execution_time_seconds=round(time.time() - start, 2),
            )
        finally:
            self._cleanup(temp_script)

        elapsed = round(time.time() - start, 2)

        if result.returncode == 0 and output_path.exists():
            return RunResult(
                success=True,
                step_path=output_path,
                error_message=None,
                raw_stderr=None,
                code_executed=injected_code,
                attempt_number=attempt,
                execution_time_seconds=elapsed,
            )

        # Failure: build a friendly message but keep raw stderr for retries.
        raw_stderr = result.stderr or ""
        if result.returncode == 0 and not output_path.exists():
            error_message = (
                "Script completed but no STEP file was created "
                "(did the code call export_step?)."
            )
        else:
            error_message = self._friendly_error(raw_stderr)

        return RunResult(
            success=False,
            step_path=None,
            error_message=error_message,
            raw_stderr=raw_stderr or error_message,
            code_executed=injected_code,
            attempt_number=attempt,
            execution_time_seconds=elapsed,
        )

    @staticmethod
    def _friendly_error(stderr: str) -> str:
        if not stderr:
            return "Script failed with no error output."
        if "ModuleNotFoundError: No module named 'build123d'" in stderr:
            return (
                "build123d not found in venv. Run: "
                ".venv/Scripts/pip install build123d"
            )
        if "export_step" in stderr:
            return "Generated code did not export the STEP file. Retrying..."
        # Otherwise return the last meaningful line of the traceback.
        lines = [ln for ln in stderr.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else stderr.strip()

    def _cleanup(self, temp_script: Path) -> None:
        if self.keep_temp:
            return
        try:
            temp_script.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    from core.step_validator import StepValidator

    runner = CodeRunner()
    validator = StepValidator()

    test_code = '''
from build123d import *
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "output.step"

with BuildPart() as part:
    Box(50, 30, 10)

export_step(part.part, str(OUTPUT_PATH))
'''

    result = runner.run(
        test_code, "test_box.step",
        on_attempt=lambda n, c: print(f"Attempt {n}"),
    )
    print("Run result:", result)

    if result.success:
        valid, msg = validator.validate(result.step_path)
        print(f"Validation: {valid} - {msg}")
