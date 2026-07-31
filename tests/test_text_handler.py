"""Validation and enrichment of free-text part descriptions."""

from __future__ import annotations

import pytest

from core.inputs.text_handler import TextHandler


# Assert on the whole appended phrase, not the bare word "millimetres" — a
# prompt that legitimately says "250 millimetres wide" would otherwise look
# like the hint had been added when it had not.
HINT = "(use millimetres for all dimensions)"


@pytest.fixture
def handler() -> TextHandler:
    return TextHandler()


def test_accepts_a_normal_description(handler):
    result = handler.prepare(
        "A mounting bracket 100x60x10mm with four 8mm holes at the corners"
    )
    assert result["type"] == "text"
    assert result["has_dimensions"] is True
    assert result["word_count"] >= 5


def test_surrounding_whitespace_is_trimmed(handler):
    result = handler.prepare("   A simple plate 100mm by 50mm by 5mm thick   ")
    assert result["prompt"].startswith("A simple plate")
    assert not result["prompt"].endswith(" ")


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_input_rejected(handler, bad):
    with pytest.raises(ValueError, match="empty"):
        handler.prepare(bad)


def test_none_rejected(handler):
    with pytest.raises(ValueError):
        handler.prepare(None)


def test_too_short_rejected(handler):
    with pytest.raises(ValueError, match="too short"):
        handler.prepare("a cube")


def test_too_long_rejected(handler):
    with pytest.raises(ValueError, match="too long"):
        handler.prepare("plate " * 500)


def test_unit_hint_appended_when_units_absent(handler):
    result = handler.prepare("A plate 100 by 50 by 5 with a hole in the centre")
    assert result["prompt"].endswith(HINT)


@pytest.mark.parametrize(
    "text",
    [
        "A plate 100mm by 50mm by 5mm thick",
        "A plate 100 cm by 50 cm by 5 cm thick",
        "A plate 4 inches by 2 inches by 1 inch thick",
        'A plate 4" by 2" by 1" thick overall',
        "A spacer 40 mm long and 30 mm outer diameter",
        "A bracket 250 millimetres wide with two slots",
        "A shaft 5 m long for a conveyor frame",
        "A plate 12 in wide and 6 in tall overall",
    ],
)
def test_unit_hint_not_appended_when_units_present(handler, text):
    assert not handler.prepare(text)["prompt"].endswith(HINT)


@pytest.mark.parametrize(
    "text",
    [
        "A mounting bracket with some holes in it",   # 'm' inside "mounting"
        "A flange with six bolt holes in a circle",   # 'in' as a preposition
        "A simple bracket with several holes in it",
    ],
)
def test_unit_words_inside_ordinary_english_are_not_units(handler, text):
    """'in' and 'm' must only count as units when a number precedes them.

    Regression: "a hole in the centre" matched the inch unit, so a prompt
    with no dimensions at all was treated as already carrying units and
    never got the millimetre hint.
    """
    assert handler.prepare(text)["prompt"].endswith(HINT)


def test_colour_words_are_stripped(handler):
    result = handler.prepare(
        "A red mounting bracket 100x60x10mm with four 8mm holes"
    )
    assert "red" not in result["prompt"].lower().split()


def test_stripping_colour_does_not_leave_double_spaces(handler):
    result = handler.prepare("A blue plate 100mm by 50mm by 5mm thick")
    assert "  " not in result["prompt"]


def test_has_dimensions_false_without_numbers(handler):
    result = handler.prepare("A simple bracket with several holes in it")
    assert result["has_dimensions"] is False
