"""Flat toolbar button rules for the Markdown pane."""

from __future__ import annotations

from typing import Sequence

from app.shell.theme_tokens import ShellThemeTokens


def flat_tool_button_qss(tokens: ShellThemeTokens, selectors: Sequence[str]) -> str:
    """Transparent border, hover fill, and a checked border.

    ``selectors`` are full QSS selectors, already escaped. This is the rule
    block the Markdown pane applies to its toolbar buttons.
    """
    idle = ",\n".join(selectors)
    checked = ",\n".join("%s:checked" % selector for selector in selectors)
    hover = ",\n".join("%s:hover" % selector for selector in selectors)
    disabled = ",\n".join("%s:disabled" % selector for selector in selectors)
    faint = tokens.gutter_text or tokens.text_muted
    return (
        "%s {\n"
        "    color: %s;\n"
        "    background: transparent;\n"
        "    border: 1px solid transparent;\n"
        "    padding: 2px 8px;\n"
        "}\n"
        "%s {\n"
        "    background-color: %s;\n"
        "    border-color: %s;\n"
        "}\n"
        "%s {\n"
        "    background-color: %s;\n"
        "}\n"
        "%s {\n"
        "    color: %s;\n"
        "}\n"
        % (
            idle,
            tokens.text_primary,
            checked,
            tokens.tree_selected_bg,
            tokens.border,
            hover,
            tokens.tree_hover_bg,
            disabled,
            faint,
        )
    )


__all__ = ["flat_tool_button_qss"]
