"""Stylesheet section builders for application-level tooltips."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def shell_section_tooltips(tokens: ShellThemeTokens) -> str:
    """Return QToolTip rules for QApplication-level styling."""
    bg = tokens.popup_bg or tokens.panel_bg
    border = tokens.popup_border or tokens.border
    return f"""QToolTip {{
    background-color: {bg};
    color: {tokens.text_primary};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
}}"""
