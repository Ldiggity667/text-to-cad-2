"""Forge3D — generation pipeline orchestrator.

Connects input handlers → prompt engineer → Ollama → code runner → validator
into a single generate() call, with LLM-driven error-correction retries.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.code_runner import CodeRunner
from core.inputs.image_handler import ImageHandler
from core.inputs.pdf_handler import PdfHandler
from core.inputs.text_handler import TextHandler
from core.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelError,
    OllamaTimeoutError,
    extract_python_code,
)
from core.prompt_engineer import PromptEngineer
from core.step_validator import StepValidator


@dataclass
class GenerationResult:
    success: bool
    step_path: Path | None
    error_message: str | None
    input_type: str           # "text", "image", or "pdf"
    model_used: str
    attempts: int
    duration_seconds: float
    code_generated: str       # final Python code
    metadata_path: Path | None  # path to .json sidecar file


class Pipeline:
    """Central coordinator for one generation request."""

    def __init__(self):
        self.ollama = OllamaClient()
        self.prompt_engineer = PromptEngineer()
        self.code_runner = CodeRunner()
        self.validator = StepValidator()
        self.text_handler = TextHandler()
        self.image_handler = ImageHandler()
        self.pdf_handler = PdfHandler()

    def generate(
        self,
        input_type: str,
        input_data: str,
        user_hint: str = "",
        model_text: str | None = None,
        model_vision: str | None = None,
        on_log: Callable[[str, str], None] | None = None,
        on_code_ready: Callable[[str], None] | None = None,
    ) -> GenerationResult:

        model_text = model_text or os.environ.get("TEXT_MODEL", "gemma4:31b")
        model_vision = model_vision or os.environ.get("VISION_MODEL", "qwen3-vl:8b")

        def log(level: str, msg: str):
            if on_log:
                on_log(level, msg)

        start_time = time.time()

        def fail(msg: str, model: str = "", code: str = "",
                 attempts: int = 0) -> GenerationResult:
            return GenerationResult(
                success=False, step_path=None, error_message=msg,
                input_type=input_type, model_used=model, attempts=attempts,
                duration_seconds=round(time.time() - start_time, 2),
                code_generated=code, metadata_path=None,
            )

        # STEP 1: Ollama availability.
        log("info", "Checking Ollama connection...")
        if not self.ollama.is_available():
            return fail(
                "Cannot connect to Ollama. Is it running? Start with: ollama serve"
            )
        log("info", "Ollama connected.")

        # STEP 2: Prepare input + build prompts.
        log("info", f"Preparing {input_type} input...")
        try:
            if input_type == "text":
                prepared = self.text_handler.prepare(input_data)
                sys_p, user_p = self.prompt_engineer.build_text_prompt(
                    prepared["prompt"])
                image_b64 = None
                model = model_text

            elif input_type == "image":
                # Two-stage: vision model DESCRIBES the part, text model CODES it.
                # Small vision models reliably describe images but stall (return
                # only "thinking", no answer) when asked to emit code directly.
                prepared = self.image_handler.prepare(input_data, user_hint)
                log("info", "Analysing image with vision model...")
                description = self._describe_image(
                    prepared["image_b64"], user_hint, model_vision, log)
                if not description:
                    if user_hint:
                        description = user_hint
                        log("warning",
                            "Vision model returned no description; using your hint only.")
                    else:
                        return fail(
                            "The vision model could not describe the image. Add a "
                            "text hint describing the part, or use the Text tab.",
                            model=model_vision)
                log("info", f"Part description: {description[:200]}")
                sys_p, user_p = self.prompt_engineer.build_text_prompt(description)
                image_b64 = None
                model = model_text

            elif input_type == "pdf":
                # Use extracted text always; optionally add a vision summary of the
                # first page. Code-gen runs on the text model (same reasoning as image).
                prepared = self.pdf_handler.prepare(input_data)
                page_img = prepared.get("page_image_b64")
                view_desc = ""
                if page_img and user_hint != "text-only":
                    log("info", "Analysing drawing with vision model...")
                    view_desc = self._describe_image(page_img, "", model_vision, log)
                combined = prepared["extracted_text"]
                if view_desc:
                    combined = (f"VISION SUMMARY OF THE DRAWING:\n{view_desc}\n\n"
                                f"{combined}")
                sys_p, user_p, _ = self.prompt_engineer.build_pdf_prompt(
                    combined, prepared["page_descriptions"], None)
                image_b64 = None
                model = model_text

            else:
                raise ValueError(f"Unknown input_type: {input_type}")

        except ValueError as e:
            return fail(str(e), model=model_text)

        # STEP 3: Generate (+ retry on failure).
        log("info", f"Calling {model} to generate build123d code...")
        current_code: str | None = None
        last_error = "Unknown error"

        for attempt in range(1, self.code_runner.max_retries + 1):
            log("info",
                f"Generation attempt {attempt} of {self.code_runner.max_retries}...")

            try:
                # Two distinct retry situations:
                #  - current_code is None: we have NO usable code yet (first try, or
                #    the model replied with prose). Re-issue the ORIGINAL prompt
                #    (with the image again for vision) plus a sterner instruction.
                #  - current_code set: code ran but failed -> error-correction prompt.
                # Always reuse the SAME model — swapping models mid-generation forces
                # a second model load and can thrash/crash a low-VRAM machine.
                if current_code is None:
                    this_user = user_p
                    if attempt > 1:
                        this_user = (
                            "IMPORTANT: Respond with ONLY a single ```python code "
                            "block containing a complete build123d script. Do not "
                            "describe the image and do not add any prose.\n\n" + user_p
                        )
                    if image_b64:
                        raw_response = self.ollama.generate_with_image(
                            this_user, sys_p, model, image_b64,
                            stream_callback=lambda c: log("stream", c),
                        )
                    else:
                        raw_response = self.ollama.generate_text(
                            this_user, sys_p, model,
                            stream_callback=lambda c: log("stream", c),
                        )
                else:
                    retry_sys, retry_user = (
                        self.prompt_engineer.build_error_retry_prompt(
                            current_code, last_error, attempt)
                    )
                    raw_response = self.ollama.generate_text(
                        retry_user, retry_sys, model,
                        stream_callback=lambda c: log("stream", c),
                    )

                current_code = extract_python_code(raw_response)
                log("info", f"Code extracted ({len(current_code)} chars).")
                if on_code_ready:
                    on_code_ready(current_code)

            except (OllamaConnectionError, OllamaTimeoutError,
                    OllamaModelError) as e:
                return fail(str(e), model=model, code=current_code or "",
                            attempts=attempt)
            except ValueError as e:
                log("warning", f"Could not extract code: {e}. Retrying...")
                last_error = str(e)
                continue

            # STEP 4: Execute.
            log("info", "Executing generated code...")
            run_result = self.code_runner.run(
                current_code,
                on_attempt=lambda n, c: log("info", "Running generated code..."),
            )

            if run_result.success:
                # STEP 5: Validate.
                log("info", "Validating STEP file...")
                is_valid, val_msg = self.validator.validate(run_result.step_path)
                if is_valid:
                    log("success",
                        f"STEP file created: {run_result.step_path} - {val_msg}")
                    metadata = self._write_metadata(
                        run_result, input_type, model, prepared)
                    return GenerationResult(
                        success=True,
                        step_path=run_result.step_path,
                        error_message=None,
                        input_type=input_type,
                        model_used=model,
                        attempts=attempt,
                        duration_seconds=round(time.time() - start_time, 2),
                        code_generated=current_code,
                        metadata_path=metadata,
                    )
                last_error = f"STEP validation failed: {val_msg}"
                log("warning", last_error)
            else:
                last_error = run_result.raw_stderr or run_result.error_message
                log("warning", f"Execution failed: {str(last_error)[:200]}")

        # All retries exhausted.
        return GenerationResult(
            success=False,
            step_path=None,
            error_message=(
                f"Failed after {self.code_runner.max_retries} attempts. "
                f"Last error: {last_error}"
            ),
            input_type=input_type,
            model_used=model,
            attempts=self.code_runner.max_retries,
            duration_seconds=round(time.time() - start_time, 2),
            code_generated=current_code or "",
            metadata_path=None,
        )

    def _describe_image(self, image_b64: str, user_hint: str, model: str,
                        log) -> str:
        """Stage 1 of the image/PDF pipeline: ask the vision model to describe the
        part in words. Returns '' if it produces nothing usable."""
        sys_d, user_d = self.prompt_engineer.build_image_description_prompt(user_hint)
        for _ in range(2):
            try:
                desc = self.ollama.generate_with_image(
                    user_d, sys_d, model, image_b64,
                    stream_callback=lambda c: log("stream", c))
            except Exception as e:  # transient vision failure -> caller falls back
                log("warning", f"Vision description failed: {e}")
                return ""
            desc = (desc or "").strip()
            if desc:
                return desc
            log("warning", "Vision model returned an empty description; retrying...")
        return ""

    def _write_metadata(self, run_result, input_type: str, model: str,
                        prepared: dict) -> Path:
        step_path = run_result.step_path
        size_kb = step_path.stat().st_size // 1024
        metadata = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "input_type": input_type,
            "model": model,
            "step_file": step_path.name,
            "file_size_kb": size_kb,
            "attempts": run_result.attempt_number,
            "code": run_result.code_executed,
        }
        json_path = step_path.with_suffix(".json")
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return json_path


if __name__ == "__main__":
    pipeline = Pipeline()

    def log_handler(level, msg):
        prefix = {"info": "i", "warning": "!", "success": "+",
                  "error": "x", "stream": ""}.get(level, "-")
        print(f"{prefix} {msg}", end="" if level == "stream" else "\n",
              flush=True)

    result = pipeline.generate(
        input_type="text",
        input_data=("A simple rectangular plate 120mm long, 80mm wide, 8mm "
                    "thick with a 20mm diameter hole in the centre"),
        on_log=log_handler,
    )

    print("\n=== RESULT ===")
    print(f"Success: {result.success}")
    print(f"STEP: {result.step_path}")
    print(f"Attempts: {result.attempts}")
    print(f"Duration: {result.duration_seconds}s")
    if not result.success:
        print(f"Error: {result.error_message}")
