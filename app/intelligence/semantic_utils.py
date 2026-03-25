"""Utilities shared by semantic engine integrations."""
from __future__ import annotations

from bisect import bisect_right
from pathlib import Path


def offset_to_line_column(source_text: str, cursor_position: int) -> tuple[int, int]:
    """Convert a 0-based character offset into Jedi-style line/column coordinates."""
    safe_position = max(0, min(cursor_position, len(source_text)))
    line_starts = _line_starts(source_text)
    line_index = bisect_right(line_starts, safe_position) - 1
    line_start = line_starts[max(0, line_index)]
    return (line_index + 1, safe_position - line_start)


def line_column_to_offset(source_text: str, line_number: int, column_number: int) -> int:
    """Convert 1-based line and 0-based column coordinates into a text offset."""
    line_starts = _line_starts(source_text)
    safe_line_number = max(1, min(line_number, len(line_starts)))
    line_start = line_starts[safe_line_number - 1]
    return max(0, min(line_start + max(0, column_number), len(source_text)))


def line_text_at(source_text: str, line_number: int) -> str:
    """Return the requested 1-based line text or an empty string."""
    lines = source_text.splitlines()
    if line_number <= 0 or line_number > len(lines):
        return ""
    return lines[line_number - 1]


def first_doc_line(doc_text: str) -> str:
    """Return the first non-empty line from a docstring payload."""
    for line in doc_text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def relative_display_path(project_root: str, file_path: str) -> str:
    """Return a project-relative display path when possible."""
    root = Path(project_root).expanduser().resolve()
    path = Path(file_path).expanduser().resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def changed_line_numbers(before_text: str, after_text: str) -> list[int]:
    """Return 1-based line numbers that changed between two payloads."""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    line_count = max(len(before_lines), len(after_lines))
    changed: list[int] = []
    for index in range(line_count):
        before_line = before_lines[index] if index < len(before_lines) else ""
        after_line = after_lines[index] if index < len(after_lines) else ""
        if before_line != after_line:
            changed.append(index + 1)
    return changed


def _line_starts(source_text: str) -> list[int]:
    starts = [0]
    for index, character in enumerate(source_text):
        if character == "\n":
            starts.append(index + 1)
    return starts
