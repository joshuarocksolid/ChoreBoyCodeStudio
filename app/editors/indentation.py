"""Helpers for detecting indentation style/size from file content."""

from __future__ import annotations

from collections import Counter


def detect_indentation_style_and_size(source_text: str, *, sample_limit: int = 200) -> tuple[str, int] | None:
    """Infer indentation style/size from leading whitespace patterns."""
    lines = source_text.splitlines()
    tab_indents = 0
    space_widths: list[int] = []

    for line in lines[:sample_limit]:
        if not line.strip():
            continue
        leading = _leading_whitespace(line)
        if not leading:
            continue
        if "\t" in leading and " " not in leading:
            tab_indents += 1
            continue
        if " " in leading and "\t" not in leading:
            space_indents = len(leading)
            if space_indents > 0:
                space_widths.append(space_indents)

    if tab_indents == 0 and not space_widths:
        return None
    if tab_indents > len(space_widths):
        return ("tabs", 1)
    if not space_widths:
        return ("tabs", 1)

    counts = Counter(space_widths)
    inferred_size = max(1, min(counts.keys(), key=lambda width: (-counts[width], width)))
    inferred_size = min(inferred_size, 8)
    return ("spaces", inferred_size)


def _leading_whitespace(line: str) -> str:
    index = 0
    while index < len(line) and line[index] in {" ", "\t"}:
        index += 1
    return line[:index]
