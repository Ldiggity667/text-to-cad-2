"""Extraction of Python from a raw LLM response.

This is the single most failure-prone step in the pipeline: local models wrap
code in fences inconsistently, prepend commentary, or answer with prose only.
"""

from __future__ import annotations

import pytest

from core.ollama_client import extract_python_code

SCRIPT = (
    "from build123d import *\n"
    "from pathlib import Path\n"
    "OUTPUT_PATH = Path(__file__).parent / 'output.step'\n"
    "with BuildPart() as part:\n"
    "    Box(10, 10, 10)\n"
    "export_step(part.part, str(OUTPUT_PATH))"
)


def test_python_fenced_block():
    response = f"Here is the part you asked for:\n\n```python\n{SCRIPT}\n```\n"
    assert extract_python_code(response).strip() == SCRIPT


def test_bare_fenced_block():
    response = f"```\n{SCRIPT}\n```"
    assert extract_python_code(response).strip() == SCRIPT


def test_fence_with_other_language_tag():
    response = f"```py\n{SCRIPT}\n```"
    assert extract_python_code(response).strip() == SCRIPT


def test_unfenced_script_is_accepted():
    assert extract_python_code(SCRIPT).strip() == SCRIPT


def test_python_fence_wins_over_a_later_bare_fence():
    response = (
        f"```python\n{SCRIPT}\n```\n\n"
        "And here is some shell:\n```\nls -la\n```"
    )
    assert "build123d" in extract_python_code(response)
    assert "ls -la" not in extract_python_code(response)


def test_surrounding_commentary_is_stripped():
    response = (
        "Sure! I'll create that for you.\n\n"
        f"```python\n{SCRIPT}\n```\n\n"
        "Let me know if you want fillets added."
    )
    extracted = extract_python_code(response)
    assert extracted.startswith("from build123d")
    assert "Let me know" not in extracted


@pytest.mark.parametrize("response", ["", "   ", "\n\n"])
def test_empty_response_rejected(response):
    with pytest.raises(ValueError):
        extract_python_code(response)


def test_prose_only_response_rejected():
    with pytest.raises(ValueError):
        extract_python_code(
            "I would need more information about the part before I can model it."
        )


def test_non_cad_code_rejected():
    """A model that returns unrelated Python must not be treated as a success."""
    with pytest.raises(ValueError, match="build123d"):
        extract_python_code("```python\nimport os\nprint(os.getcwd())\n```")


def test_cadquery_code_rejected():
    """CadQuery is a different library; running it would fail downstream."""
    with pytest.raises(ValueError):
        extract_python_code(
            "```python\nimport cadquery as cq\nr = cq.Workplane('XY').box(1,1,1)\n```"
        )
