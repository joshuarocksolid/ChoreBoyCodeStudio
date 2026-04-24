"""Helpers for detecting indentation style/size from file content."""

from __future__ import annotations

from collections import Counter
from math import gcd
from typing import Optional

_MIN_DETECTABLE_SIZE = 2
_MAX_DETECTABLE_SIZE = 8


def detect_indentation_style_and_size(source_text: str, *, sample_limit: int = 200) -> Optional[tuple[str, int]]:
    """Infer indentation style/size from leading whitespace patterns.

    The size is inferred from the *unit* of indentation (the change in leading
    whitespace between consecutive nesting levels), not the most common depth.
    Falls back to the GCD of all observed leading widths when no positive
    deltas are present (e.g. a file containing only top-level statements with
    consistent indentation). The result is clamped to [2, 8].
    """
    lines = source_text.splitlines()[:sample_limit]
    tab_indent_lines = 0
    space_widths: list[int] = []
    for line in lines:
        if not line.strip():
            continue
        leading = _leading_whitespace(line)
        if not leading:
            continue
        if leading[0] == "\t":
            tab_indent_lines += 1
            continue
        if " " in leading and "\t" not in leading:
            space_widths.append(len(leading))

    if tab_indent_lines == 0 and not space_widths:
        return None
    if tab_indent_lines > len(space_widths):
        return ("tabs", 1)
    if not space_widths:
        return ("tabs", 1)

    size = _infer_indent_unit(space_widths)
    if size is None:
        return None
    return ("spaces", size)


def _infer_indent_unit(widths: list[int]) -> Optional[int]:
    deltas = _positive_deltas(widths)
    if deltas:
        counts = Counter(deltas)
        size = min(counts.keys(), key=lambda value: (-counts[value], value))
    else:
        size = _gcd_of(widths)
    if size <= 0:
        return None
    return max(_MIN_DETECTABLE_SIZE, min(size, _MAX_DETECTABLE_SIZE))


def _positive_deltas(widths: list[int]) -> list[int]:
    deltas: list[int] = []
    for previous, current in zip(widths, widths[1:]):
        delta = current - previous
        if delta > 0:
            deltas.append(delta)
    return deltas


def _gcd_of(values: list[int]) -> int:
    result = 0
    for value in values:
        result = gcd(result, value)
    return result


def _leading_whitespace(line: str) -> str:
    index = 0
    while index < len(line) and line[index] in {" ", "\t"}:
        index += 1
    return line[:index]
