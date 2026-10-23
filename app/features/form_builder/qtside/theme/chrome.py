"""Colours the Start screen and dialogs paint with.

Callers fill this from shell theme tokens. This module does not import the shell.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormChrome:
    """One snapshot of the builder chrome roles."""

    window: str
    panel: str
    text: str
    muted: str
    faint: str
    border: str
    accent: str
    row_hover: str
    input: str
    error: str
    focus_width: int


def chrome_from_values(
    *,
    window: str,
    panel: str,
    text: str,
    muted: str,
    faint: str,
    border: str,
    accent: str,
    row_hover: str,
    input_bg: str,
    error: str,
    focus_width: int,
) -> FormChrome:
    return FormChrome(
        window=window,
        panel=panel or window,
        text=text,
        muted=muted or text,
        faint=faint or muted or text,
        border=border,
        accent=accent,
        row_hover=row_hover or panel or window,
        input=input_bg or panel or window,
        error=error or accent,
        focus_width=focus_width if focus_width > 0 else 1,
    )
