"""WCAG relative-luminance and contrast-ratio helpers.

Pure helpers used to audit and protect theme token contrast.  Kept Qt-free so
they can be reused in unit tests without spinning up a QApplication.
"""

from __future__ import annotations

# Per WCAG 2.x: AA requires 4.5:1 for normal-size text (>= 14pt regular or
# >= 12pt bold) and 3:1 for large text.  AAA raises that to 7:1 / 4.5:1.
WCAG_AA_NORMAL_TEXT_RATIO = 4.5
WCAG_AA_LARGE_TEXT_RATIO = 3.0
WCAG_AAA_NORMAL_TEXT_RATIO = 7.0


def _channel_to_linear(channel_srgb_8bit: int) -> float:
    """Convert one 0-255 sRGB channel to its linear-light equivalent."""
    c = channel_srgb_8bit / 255.0
    if c <= 0.03928:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    raw = hex_color.strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raise ValueError(f"Unsupported color literal: {hex_color!r}")
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Unsupported color literal: {hex_color!r}") from exc


def relative_luminance(hex_color: str) -> float:
    """Return WCAG relative luminance for an RGB hex color (e.g. ``"#1F2428"``)."""
    r, g, b = _parse_hex(hex_color)
    return (
        0.2126 * _channel_to_linear(r)
        + 0.7152 * _channel_to_linear(g)
        + 0.0722 * _channel_to_linear(b)
    )


def contrast_ratio(foreground_hex: str, background_hex: str) -> float:
    """Return WCAG contrast ratio (>= 1.0) for foreground vs background colors."""
    fg = relative_luminance(foreground_hex)
    bg = relative_luminance(background_hex)
    lighter = max(fg, bg)
    darker = min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


def meets_wcag_aa_normal(foreground_hex: str, background_hex: str) -> bool:
    """Return True when contrast meets WCAG AA for normal-size body text."""
    return contrast_ratio(foreground_hex, background_hex) >= WCAG_AA_NORMAL_TEXT_RATIO
