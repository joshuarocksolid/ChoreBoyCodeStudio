"""Shared control styling for shell widgets."""

from __future__ import annotations

from urllib.parse import quote

from app.shell.theme_tokens import ShellThemeTokens


def _checkbox_checked_indicator_data_uri(accent: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        f'<rect width="14" height="14" rx="3" fill="{accent}"/>'
        '<path d="M3.5 7.2 L6 9.7 L10.5 4.5" stroke="#FFFFFF" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


def shell_section_checkbox_indicators(tokens: ShellThemeTokens) -> str:
    """Return shell-wide QCheckBox indicator styling."""
    border_width = tokens.focus_border_width
    checked_image = _checkbox_checked_indicator_data_uri(tokens.accent)
    return f"""/* -- Check boxes (indicator) ------------------------------------------- */
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: {border_width}px solid {tokens.border};
    border-radius: 3px;
    background: {tokens.input_bg};
}}
QCheckBox::indicator:hover {{
    border-color: {tokens.accent};
}}
QCheckBox::indicator:checked {{
    border: {border_width}px solid {tokens.accent};
    background: {tokens.accent};
    image: url("{checked_image}");
}}
QCheckBox::indicator:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
}}
QCheckBox::indicator:checked:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    image: none;
}}
"""
