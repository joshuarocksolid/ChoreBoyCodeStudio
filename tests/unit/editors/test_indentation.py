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
