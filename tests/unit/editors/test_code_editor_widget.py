"""Unit tests for code editor text transform helpers."""

from __future__ import annotations

import pytest

from app.editors.text_editing import (
    FLAT_PYTHON_CONFIDENCE_HIGH,
    FLAT_PYTHON_CONFIDENCE_MEDIUM,
    indent_lines,
    looks_like_flat_python_paste,
    next_line_indentation,
    outdent_lines,
    repair_flat_python_indentation,
    smart_backspace_columns,
    toggle_comment_lines,
)

pytestmark = pytest.mark.unit


def test_indent_and_outdent_lines_round_trip() -> None:
    original = "a = 1\nb = 2"
    indented = indent_lines(original, indent_text="    ")
    assert indented == "    a = 1\n    b = 2"
    assert outdent_lines(indented, indent_text="    ") == original


def test_toggle_comment_lines_comments_and_uncomments_block() -> None:
    original = "def run():\n    return 1"
    commented = toggle_comment_lines(original)
    assert commented == "#def run():\n#    return 1"
    uncommented = toggle_comment_lines(commented)
    assert uncommented == original


def test_toggle_comment_lines_ignores_empty_lines() -> None:
    original = "value = 1\n\nprint(value)"
    commented = toggle_comment_lines(original)
    assert commented == "#value = 1\n\n#print(value)"


def test_toggle_comment_lines_uncomments_only_column_zero_prefix() -> None:
    original = "    # inside block\n#top_level"
    toggled = toggle_comment_lines(original)
    assert toggled == "#    # inside block\n##top_level"


def test_indent_and_outdent_support_tab_indent_text() -> None:
    original = "alpha = 1\nbeta = 2"
    indented = indent_lines(original, indent_text="\t")
    assert indented == "\talpha = 1\n\tbeta = 2"
    assert outdent_lines(indented, indent_text="\t") == original


def test_smart_backspace_columns_uses_indent_boundaries_for_spaces() -> None:
    assert smart_backspace_columns("        value = 1", 8, indent_text="    ") == 4
    assert smart_backspace_columns("      value = 1", 6, indent_text="    ") == 2


def test_smart_backspace_columns_only_triggers_in_leading_whitespace() -> None:
    assert smart_backspace_columns("    value = 1", 10, indent_text="    ") == 0
    assert smart_backspace_columns("\t\tvalue = 1", 2, indent_text="\t") == 1


def test_next_line_indentation_carries_and_indents_after_colon() -> None:
    assert next_line_indentation("    if ready:", indent_text="    ") == "        "
    assert next_line_indentation("    value = 1", indent_text="    ") == "    "
    assert next_line_indentation("\tif ready:", indent_text="\t") == "\t\t"


def test_repair_flat_python_indentation_handles_nested_if_else() -> None:
    result = repair_flat_python_indentation(
        'def describe(value):\nif value > 10:\nreturn "large"\nelse:\nreturn "small"\n'
    )

    assert result.text == (
        'def describe(value):\n'
        '    if value > 10:\n'
        '        return "large"\n'
        '    else:\n'
        '        return "small"\n'
    )
    assert result.changed is True
    assert result.parse_ok is True
    assert result.confidence == FLAT_PYTHON_CONFIDENCE_HIGH


def test_repair_flat_python_indentation_aligns_try_except_finally() -> None:
    result = repair_flat_python_indentation(
        'def load():\ntry:\nvalue = int("1")\nreturn value\nexcept ValueError:\nreturn 0\nfinally:\nprint("done")'
    )

    assert result.text == (
        'def load():\n'
        '    try:\n'
        '        value = int("1")\n'
        '        return value\n'
        '    except ValueError:\n'
        '        return 0\n'
        '    finally:\n'
        '        print("done")'
    )
    assert result.parse_ok is True


def test_repair_flat_python_indentation_handles_loops_and_terminal_dedent() -> None:
    result = repair_flat_python_indentation(
        "def run(items):\nfor item in items:\nif item:\nbreak\ncontinue\nwhile False:\nbreak\nreturn items"
    )

    assert result.text == (
        "def run(items):\n"
        "    for item in items:\n"
        "        if item:\n"
        "            break\n"
        "        continue\n"
        "    while False:\n"
        "        break\n"
        "    return items"
    )
    assert result.parse_ok is True


def test_repair_flat_python_indentation_handles_async_def_and_with() -> None:
    result = repair_flat_python_indentation(
        "async def read(path):\nwith open(path) as handle:\nreturn handle.read()"
    )

    assert result.text == (
        "async def read(path):\n"
        "    with open(path) as handle:\n"
        "        return handle.read()"
    )
    assert result.parse_ok is True


def test_repair_flat_python_indentation_resets_after_blank_before_new_def() -> None:
    result = repair_flat_python_indentation("def first():\nreturn 1\n\ndef second():\nreturn 2\n")

    assert result.text == "def first():\n    return 1\n\ndef second():\n    return 2\n"
    assert result.parse_ok is True


def test_repair_flat_python_indentation_strips_consistent_pdf_line_numbers() -> None:
    result = repair_flat_python_indentation("1 def first():\n2 return 1\n")

    assert result.text == "def first():\n    return 1\n"
    assert result.parse_ok is True


def test_repair_flat_python_indentation_ignores_inconsistent_pdf_line_numbers() -> None:
    result = repair_flat_python_indentation("1 def first():\nreturn 1\n")

    assert result.text == "1 def first():\nreturn 1\n"
    assert result.reason == "not a flat Python paste"


def test_flat_python_detection_rejects_already_indented_text() -> None:
    assert not looks_like_flat_python_paste("def first():\n    return 1\n")


def test_flat_python_detection_rejects_non_python_prose() -> None:
    assert not looks_like_flat_python_paste("This is a heading:\nThis is another sentence.")


def test_repair_flat_python_indentation_supports_tab_indent_text() -> None:
    result = repair_flat_python_indentation("def first():\nreturn 1", indent_text="\t")

    assert result.text == "def first():\n\treturn 1"
    assert result.parse_ok is True


def test_repair_flat_python_indentation_reports_failed_parse_confidence() -> None:
    result = repair_flat_python_indentation("def broken(:\nreturn 1")

    assert result.parse_ok is False
    assert result.confidence in {FLAT_PYTHON_CONFIDENCE_MEDIUM, "low"}
