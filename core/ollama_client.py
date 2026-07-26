"""Forge3D — Ollama client.

This module is the ONLY place in the codebase that communicates with Ollama.
All other modules call this one — never call Ollama directly elsewhere.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable

import requests


# ── Custom exceptions ──────────────────────────────────────────────────────
class OllamaError(Exception):
    """Base class for all Ollama-related errors."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama cannot be reached."""


class OllamaModelError(OllamaError):
    """Raised when the requested model is missing or invalid."""


class OllamaTimeoutError(OllamaError):
    """Raised when an Ollama request times out."""


# Default per-request timeouts: (connect, read). Reads can be slow because the
# qwen3-vl "thinking" models generate a long internal monologue before the answer.
_CONNECT_TIMEOUT = 5
_READ_TIMEOUT = int(os.environ.get("OLLAMA_READ_TIMEOUT", "300"))

# Context window. qwen3-vl thinking models need room for ~3k tokens of "thinking"
# PLUS the actual answer; the default 4096 gets fully consumed by thinking and the
# model returns an EMPTY response. 8192 reliably leaves room for the code.
_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


class OllamaClient:
    """Thin REST client around a local Ollama server."""

    def __init__(self, host: str | None = None):
        if host is None:
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.host = host.rstrip("/")
        self.session = requests.Session()
        self.timeout = (_CONNECT_TIMEOUT, _READ_TIMEOUT)

    # ── Health / discovery ────────────────────────────────────────────────
    def is_available(self) -> bool:
        """Return True if the Ollama server answers. Never raises."""
        try:
            r = self.session.get(f"{self.host}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return the list of installed model names, or [] on any error."""
        try:
            r = self.session.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def model_sizes(self) -> dict[str, int]:
        """Return {model_name: size_bytes} for installed models, or {} on error."""
        try:
            r = self.session.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            return {m["name"]: int(m.get("size", 0))
                    for m in data.get("models", [])}
        except Exception:
            return {}

    # ── Generation ────────────────────────────────────────────────────────
    def generate_text(
        self,
        prompt: str,
        system: str,
        model: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Stream a text completion from `model` and return the full response."""
        body = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": True,
            # These models support a "thinking" phase. think=False is not always
            # honoured, so we also enlarge num_ctx to leave room for the answer
            # after the thinking — otherwise the response comes back empty.
            "think": False,
            "options": {"num_ctx": _NUM_CTX},
        }
        return self._stream_generate(body, stream_callback)

    def generate_with_image(
        self,
        prompt: str,
        system: str,
        model: str,
        image_b64: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Stream a vision completion (prompt + one base64 image)."""
        body = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "images": [image_b64],
            "stream": True,
            "think": False,
            "options": {"num_ctx": _NUM_CTX},
        }
        return self._stream_generate(body, stream_callback)

    # ── Internal ──────────────────────────────────────────────────────────
    def _stream_generate(
        self,
        body: dict,
        stream_callback: Callable[[str], None] | None,
    ) -> str:
        url = f"{self.host}/api/generate"
        model = body.get("model", "?")
        try:
            resp = self.session.post(
                url, json=body, stream=True, timeout=self.timeout
            )
        except requests.Timeout as e:
            raise OllamaTimeoutError(
                f"Ollama request timed out connecting to {self.host}."
            ) from e
        except (requests.ConnectionError, ConnectionRefusedError) as e:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.host}. Is it running? "
                f"Start with: ollama serve"
            ) from e

        if resp.status_code == 404:
            raise OllamaModelError(
                f"Model '{model}' not found. Install with: ollama pull {model}"
            )
        if resp.status_code >= 400:
            # Try to surface the server message.
            detail = ""
            try:
                detail = resp.json().get("error", "")
            except Exception:
                detail = resp.text[:200]
            if "model" in detail.lower() and "not found" in detail.lower():
                raise OllamaModelError(
                    f"Model '{model}' not found. Install with: ollama pull {model}"
                )
            raise OllamaError(f"Ollama returned HTTP {resp.status_code}: {detail}")

        chunks: list[str] = []
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "error" in obj:
                    err = obj["error"]
                    if "not found" in err.lower():
                        raise OllamaModelError(
                            f"Model '{model}' not found. "
                            f"Install with: ollama pull {model}"
                        )
                    raise OllamaError(f"Ollama error: {err}")

                piece = obj.get("response", "")
                if piece:
                    chunks.append(piece)
                    if stream_callback:
                        stream_callback(piece)

                if obj.get("done"):
                    break
        except requests.Timeout as e:
            raise OllamaTimeoutError(
                "Ollama timed out while streaming the response."
            ) from e
        except requests.ConnectionError as e:
            raise OllamaConnectionError(
                "Lost connection to Ollama while streaming."
            ) from e
        finally:
            resp.close()

        return "".join(chunks)


# ── Code extraction helper ─────────────────────────────────────────────────
def extract_python_code(llm_response: str) -> str:
    """Extract a build123d Python script from a raw LLM response.

    Handles, in order:
      1. ```python ... ``` fenced block
      2. ``` ... ``` fenced block
      3. No fences but contains "from build123d"
      4. Otherwise → ValueError
    The extracted code must reference build123d.
    """
    if not llm_response or not llm_response.strip():
        raise ValueError("No Python code found in LLM response")

    code: str | None = None

    # 1. ```python ... ```
    m = re.search(r"```python\s*\n(.*?)```", llm_response, re.DOTALL | re.IGNORECASE)
    if m:
        code = m.group(1)
    else:
        # 2. ``` ... ``` (any/no language tag)
        m = re.search(r"```[^\n]*\n(.*?)```", llm_response, re.DOTALL)
        if m:
            code = m.group(1)

    # 3. No fences but looks like a build123d script
    if code is None and "from build123d" in llm_response:
        code = llm_response

    if code is None:
        raise ValueError("No Python code found in LLM response")

    code = code.strip()

    if "build123d" not in code:
        raise ValueError(
            "Extracted code does not reference build123d - likely not a CAD script"
        )

    return code


if __name__ == "__main__":
    client = OllamaClient()
    if client.is_available():
        models = client.list_models()
        print(f"Ollama running. Models: {models}")
        text_model = os.environ.get("TEXT_MODEL", "gemma4:31b")
        response = client.generate_text(
            prompt="Write a single Python statement that creates a 10mm cube using build123d.",
            system="You are a build123d expert. Respond with only Python code.",
            model=text_model,
            stream_callback=lambda chunk: print(chunk, end="", flush=True),
        )
        print("\n--- Full response ---")
        print(response)
        try:
            code = extract_python_code(response)
            print("--- Extracted code ---")
            print(code)
        except ValueError as e:
            print(f"(code extraction note: {e})")
    else:
        print("Ollama not available. Start with: ollama serve")
