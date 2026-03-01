"""Unit tests for code editor text transform helpers."""

from __future__ import annotations

import pytest

from app.editors.code_editor_widget import indent_lines, outdent_lines, toggle_comment_lines

pytestmark = pytest.mark.unit


def test_indent_and_outdent_lines_round_trip() -> None:
    original = "a = 1\nb = 2"
    indented = indent_lines(original, indent_text="    ")
    assert indented == "    a = 1\n    b = 2"
    assert outdent_lines(indented, indent_text="    ") == original


def test_toggle_comment_lines_comments_and_uncomments_block() -> None:
    original = "def run():\n    return 1"
    commented = toggle_comment_lines(original)
    assert commented == "# def run():\n    # return 1"
    uncommented = toggle_comment_lines(commented)
    assert uncommented == original


def test_toggle_comment_lines_ignores_empty_lines() -> None:
    original = "value = 1\n\nprint(value)"
    commented = toggle_comment_lines(original)
    assert commented == "# value = 1\n\n# print(value)"
