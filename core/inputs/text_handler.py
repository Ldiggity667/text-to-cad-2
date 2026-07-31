"""Forge3D — text input handler.

Validates and lightly enriches a free-text part description. Does NOT call
Ollama — it only prepares data for the pipeline.
"""

from __future__ import annotations

import re


# Unit may be glued to a digit ("10mm") or stand alone ("10 cm").
#
# A unit only counts when a number comes before it. Allowing whitespace on
# the left was too permissive: "in" then matched the preposition in "a hole
# in the centre", so a prompt with no units at all looked like it had them
# and never got the millimetre hint appended. Anchoring on a leading digit
# is what distinguishes "100 in" from "hole in the centre".
_UNIT_PATTERN = re.compile(
    r'\d\s*'
    r'(?:mm|millimet(?:re|er)s?|cm|centimet(?:re|er)s?|'
    r'inch(?:es)?|in|m|met(?:re|er)s?)\b'
    r'|\d\s*["″]',  # inch/double-prime marks, e.g. 4"
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"\d")
# Common colour words to strip — STEP export does not carry colour meaningfully.
_COLOUR_WORDS = [
    "red", "green", "blue", "yellow", "orange", "purple", "violet", "pink",
    "black", "white", "grey", "gray", "brown", "cyan", "magenta", "gold",
    "silver", "bronze", "copper",
]
_COLOUR_PATTERN = re.compile(
    r"\b(?:" + "|".join(_COLOUR_WORDS) + r")(?:\s+colou?red)?\b",
    re.IGNORECASE,
)


class TextHandler:
    """Prepare a text prompt for the generation pipeline."""

    def prepare(self, raw_input: str) -> dict:
        if raw_input is None:
            raise ValueError("No text provided.")

        prompt = raw_input.strip()

        if not prompt:
            raise ValueError("Text prompt is empty.")

        word_count = len(prompt.split())
        if word_count < 5:
            raise ValueError(
                "Text prompt is too short — describe the part in at least 5 words."
            )
        if len(prompt) > 2000:
            raise ValueError(
                "Text prompt is too long — keep it under 2000 characters."
            )

        # Strip colour references (collapse the resulting double spaces).
        cleaned = _COLOUR_PATTERN.sub("", prompt)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned:
            prompt = cleaned

        has_dimensions = bool(_NUMBER_PATTERN.search(prompt))

        # Append a unit hint if no units are mentioned anywhere.
        if not _UNIT_PATTERN.search(prompt):
            prompt = prompt + " (use millimetres for all dimensions)"

        return {
            "type": "text",
            "prompt": prompt,
            "word_count": word_count,
            "has_dimensions": has_dimensions,
        }


if __name__ == "__main__":
    th = TextHandler()
    print(th.prepare(
        "A red mounting bracket 100x60x10 with four 8 diameter holes at corners"
    ))
