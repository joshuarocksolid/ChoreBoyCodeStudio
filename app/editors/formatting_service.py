"""Deterministic built-in formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatResult:
    """Formatting result payload."""

    formatted_text: str
    changed: bool


def format_text_basic(
    source_text: str,
    *,
    trim_trailing_whitespace: bool = True,
    ensure_final_newline: bool = True,
) -> FormatResult:
    """Apply lightweight deterministic text formatting."""
    lines = source_text.splitlines()
    if trim_trailing_whitespace:
        lines = [line.rstrip(" \t") for line in lines]
    formatted = "\n".join(lines)
    if ensure_final_newline and formatted:
        formatted = f"{formatted}\n"
    changed = formatted != source_text
    return FormatResult(formatted_text=formatted, changed=changed)
