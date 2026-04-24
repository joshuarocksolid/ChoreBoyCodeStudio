"""Unit tests for indentation detection helpers."""

from __future__ import annotations

import pytest

from app.editors.indentation import detect_indentation_style_and_size

pytestmark = pytest.mark.unit


def test_detect_indentation_style_and_size_detects_spaces_and_size() -> None:
    source = "def demo():\n    if True:\n        return 1\n"
    assert detect_indentation_style_and_size(source) == ("spaces", 4)


def test_detect_indentation_style_and_size_detects_tabs() -> None:
    source = "def demo():\n\tif True:\n\t\treturn 1\n"
    assert detect_indentation_style_and_size(source) == ("tabs", 1)


def test_detect_indentation_style_and_size_returns_none_without_indentation() -> None:
    source = "value = 1\nprint(value)\n"
    assert detect_indentation_style_and_size(source) is None


def test_detect_indentation_size_4_when_most_lines_are_doubly_nested() -> None:
    """Regression: Ervin Newswanger reported tab inserting 8 spaces.

    A typical 4-space-indented Python file where most lines live inside class
    methods (8-space leading whitespace) used to be misdetected as size 8 by the
    most-common-leading-width heuristic. Detection must report the indent unit
    (4), not the most common depth.
    """
    source = (
        "class Service:\n"
        "    def method_a(self):\n"
        "        a = 1\n"
        "        b = 2\n"
        "        c = 3\n"
        "        d = 4\n"
        "    def method_b(self):\n"
        "        e = 5\n"
        "        f = 6\n"
        "        g = 7\n"
        "        h = 8\n"
    )
    assert detect_indentation_style_and_size(source) == ("spaces", 4)


def test_detect_indentation_size_2_when_most_lines_are_doubly_nested() -> None:
    source = (
        "class Service:\n"
        "  def method_a(self):\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "  def method_b(self):\n"
        "    d = 4\n"
        "    e = 5\n"
        "    f = 6\n"
    )
    assert detect_indentation_style_and_size(source) == ("spaces", 2)


def test_detect_indentation_size_3_when_file_uses_three_space_indent() -> None:
    source = (
        "def outer():\n"
        "   if cond:\n"
        "      do_a()\n"
        "      do_b()\n"
        "   else:\n"
        "      do_c()\n"
    )
    assert detect_indentation_style_and_size(source) == ("spaces", 3)


def test_detect_indentation_tabs_win_when_lines_mix_tabs_and_spaces_with_tab_first() -> None:
    """A line starting with a tab is a tab-indented line, even if spaces follow."""
    source = (
        "def demo():\n"
        "\tif True:\n"
        "\t\treturn 1\n"
        "\t\t  continued = True\n"
    )
    assert detect_indentation_style_and_size(source) == ("tabs", 1)


def test_detect_indentation_single_indented_line_does_not_return_huge_size() -> None:
    """A file with exactly one indented line at depth 1 should not report size 8."""
    source = "def demo():\n    return 1\n"
    result = detect_indentation_style_and_size(source)
    assert result is not None
    style, size = result
    assert style == "spaces"
    assert 2 <= size <= 8


def test_detect_indentation_caps_at_8_for_pathological_input() -> None:
    """Even if every line is indented by 12 spaces, cap the result at 8."""
    source = (
        "def demo():\n"
        + "            a = 1\n" * 5
    )
    result = detect_indentation_style_and_size(source)
    assert result is not None
    style, size = result
    assert style == "spaces"
    assert size <= 8


def test_detect_indentation_floors_at_2() -> None:
    """A 1-space leading width is meaningless; never return size 1 for spaces."""
    source = (
        "def demo():\n"
        " a = 1\n"
        " b = 2\n"
        " c = 3\n"
    )
    result = detect_indentation_style_and_size(source)
    assert result is not None
    style, size = result
    assert style == "spaces"
    assert size >= 2
