"""Builder chrome colours (UX-TOK-001, UX-TOK-002, UX-ISO-003).

Hex values for the builder live here. Callers pass the theme flags.
This module does not import the shell.
"""

from __future__ import annotations

from typing import Optional, Tuple

PAGE_TITLE_HEIGHT = 22
PAGE_TITLE_FILL = "#E4E4E4"
PAGE_TITLE_GLYPH = "#6B6B6B"


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


__all__ = [
    "PAGE_TITLE_FILL",
    "PAGE_TITLE_GLYPH",
    "PAGE_TITLE_HEIGHT",
    "backdrop_colors",
    "page_shadow_rgba",
]
