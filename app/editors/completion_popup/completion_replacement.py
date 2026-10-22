"""Replacement range for accepting a completion: only the typed prefix."""

from __future__ import annotations


def identifier_span_before(source_text: str, cursor_position: int) -> tuple[int, int]:
    """Return ``[start, end)`` covering the identifier immediately before the cursor."""

    end = max(0, min(cursor_position, len(source_text)))
    start = end
    while start > 0:
        ch = source_text[start - 1]
        if ch.isalnum() or ch == "_":
            start -= 1
            continue
        break
    return start, end


def resolve_insert_replacement_range(source_text: str, cursor_position: int) -> tuple[int, int]:
    """Return the typed prefix to replace; text after the cursor is never touched."""

    return identifier_span_before(source_text, cursor_position)
