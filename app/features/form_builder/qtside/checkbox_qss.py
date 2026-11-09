"""Check-box indicators for form-builder surfaces. Same drawing as the shell section."""

from __future__ import annotations

from urllib.parse import quote


def checkbox_indicators(tokens: object) -> str:
    border_width = int(getattr(tokens, "focus_border_width", 1) or 1)
    accent = str(getattr(tokens, "accent", "") or "")
    border = str(getattr(tokens, "border", "") or "")
    input_bg = str(getattr(tokens, "input_bg", "") or "")
    panel_bg = str(getattr(tokens, "panel_bg", "") or "")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        '<rect width="14" height="14" rx="3" fill="%s"/>'
        '<path d="M3.5 7.2 L6 9.7 L10.5 4.5" stroke="white" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ) % accent
    image = "data:image/svg+xml," + quote(svg, safe="")
    return (
        "QCheckBox::indicator { width: 14px; height: 14px; border: %dpx solid %s; border-radius: 3px; background: %s; }"
        "QCheckBox::indicator:hover { border-color: %s; }"
        "QCheckBox::indicator:checked { border: %dpx solid %s; background: %s; image: url(\"%s\"); }"
        "QCheckBox::indicator:disabled { background: %s; border-color: %s; }"
        "QCheckBox::indicator:checked:disabled { border: %dpx solid %s; background: %s; image: url(\"%s\"); }"
    ) % (
        border_width, border, input_bg,
        accent,
        border_width, accent, accent, image,
        panel_bg, border,
        border_width, accent, accent, image,
    )
