"""Colours of the style sheet drawer that the shared chrome has no role for (``fb.ok``)."""

from __future__ import annotations

# fb.ok: light, dark, high contrast light, high contrast dark.
_OK = ("#1A7F37", "#3FB950", "#0B5D1E", "#7EE787")


def ok_color(chrome: object) -> str:
    dark = bool(getattr(chrome, "is_dark", False))
    contrast = bool(getattr(chrome, "is_high_contrast", False))
    return _OK[(2 if contrast else 0) + (1 if dark else 0)]

#: Starting colours of the drawer's Insert helpers (UX-STYLE-006).
INSERT_COLOUR = "#1A7F37"
GRADIENT_FIRST = "#FFFFFF"
GRADIENT_SECOND = "#1A7F37"
