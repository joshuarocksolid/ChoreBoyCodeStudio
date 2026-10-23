"""Builder chrome colours: dialog/Start roles (FormChrome) and canvas chrome
(UX-TOK-001, UX-TOK-002, UX-ISO-003).

Hex values for the builder live here. Callers fill roles from shell theme
tokens and pass theme flags. This module does not import the shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

PAGE_TITLE_HEIGHT = 22
PAGE_TITLE_FILL = "#E4E4E4"
PAGE_TITLE_GLYPH = "#6B6B6B"
PAGE_TITLE_TEXT = "#3C3C3C"


def backdrop_colors(*, is_dark: bool, is_high_contrast: bool) -> Tuple[str, str]:
    """Backdrop fill and 1 px dot colour. High contrast has no dots."""
    if is_high_contrast:
        return ("#000000", "") if is_dark else ("#FFFFFF", "")
    if is_dark:
        return ("#16191D", "#262B31")
    return ("#E9EBEF", "#D3D8DF")


def page_shadow_rgba(*, is_dark: bool, is_high_contrast: bool) -> Optional[Tuple[int, int, int, int]]:
    """Drop shadow for the page card. High contrast uses a border instead."""
    if is_high_contrast:
        return None
    if is_dark:
        return (0, 0, 0, 115)
    return (16, 24, 40, 26)


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
    on_accent: str = "#FFFFFF"


def on_accent_for(accent: str) -> str:
    """Text on an accent fill: white, or near-black when white is under 4.5 : 1."""
    if _contrast(accent, "#FFFFFF") >= 4.5:
        return "#FFFFFF"
    return "#0B1020"


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    if len(value) != 6:
        return 0.0
    channels = []
    for index in (0, 2, 4):
        channel = int(value[index:index + 2], 16) / 255.0
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


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
        on_accent=on_accent_for(accent),
    )
