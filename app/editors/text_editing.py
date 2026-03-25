"""Pure text-editing helper functions shared by editor widgets/tests."""

from __future__ import annotations

import difflib


def indent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Indent every non-empty line in text."""
    lines = text.splitlines()
    return "\n".join(f"{indent_text}{line}" if line.strip() else line for line in lines)


def outdent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Outdent lines by one indentation unit when present."""
    lines = text.splitlines()
    outdented: list[str] = []
    for line in lines:
        if line.startswith(indent_text):
            outdented.append(line[len(indent_text) :])
        elif line.startswith("\t"):
            outdented.append(line[1:])
        elif line.startswith(" "):
            outdented.append(line[1:])
        else:
            outdented.append(line)
    return "\n".join(outdented)


def toggle_comment_lines(text: str, *, comment_prefix: str = "#") -> str:
    """Toggle Python line comments for multi-line selection."""
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return text
    should_uncomment = all(line.startswith("#") for line in non_empty)

    transformed: list[str] = []
    for line in lines:
        if not line.strip():
            transformed.append(line)
            continue
        if should_uncomment:
            transformed.append(line[1:] if line.startswith("#") else line)
        else:
            transformed.append(f"{comment_prefix}{line}")
    return "\n".join(transformed)


def next_line_indentation(line_prefix: str, *, indent_text: str = "    ") -> str:
    """Compute indentation for a newline after ``line_prefix``."""
    leading = line_prefix[: len(line_prefix) - len(line_prefix.lstrip(" \t"))]
    stripped = line_prefix.rstrip()
    if stripped.endswith(":"):
        return f"{leading}{indent_text}"
    return leading


def smart_backspace_columns(line_text: str, cursor_column: int, *, indent_text: str = "    ") -> int:
    """Return how many columns smart-backspace should remove."""
    if cursor_column <= 0:
        return 0
    prefix = line_text[:cursor_column]
    if not prefix:
        return 0
    if prefix.strip():
        return 0

    if indent_text == "\t":
        return 1 if prefix.endswith("\t") else 0

    if "\t" in prefix:
        return 0
    unit = max(1, len(indent_text))
    remove_count = len(prefix) % unit
    if remove_count == 0:
        remove_count = unit
    if not prefix.endswith(" " * remove_count):
        return 0
    return remove_count


def map_offset_through_text_change(original_text: str, updated_text: str, offset: int) -> int:
    """Map a character offset from ``original_text`` into ``updated_text``."""
    if offset <= 0:
        return 0
    if offset >= len(original_text):
        return len(updated_text)

    safe_offset = max(0, min(offset, len(original_text)))
    matcher = difflib.SequenceMatcher(a=original_text, b=updated_text, autojunk=False)
    for tag, original_start, original_end, updated_start, updated_end in matcher.get_opcodes():
        if safe_offset < original_start:
            delta = safe_offset - original_start
            return max(0, updated_start + delta)
        if tag == "equal":
            if safe_offset <= original_end:
                return updated_start + (safe_offset - original_start)
            continue
        if safe_offset <= original_end:
            return updated_end
    return len(updated_text)
