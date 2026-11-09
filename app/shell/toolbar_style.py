"""Toolbar button rules shared with the Markdown pane.

The form tab calls these instead of keeping a second copy of the Markdown
toolbar stylesheet.
"""

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


def mode_group_qss(tokens: ShellThemeTokens, group: str) -> str:
    """The Markdown Design-style mode group.

    ``group`` is the object name with dots escaped for QSS (``a\\.b``).
    """
    faint = tokens.gutter_text or tokens.text_muted
    border = tokens.border
    return (
        "QWidget#%s { border: 1px solid %s; border-radius: 4px; background: %s; }"
        "QWidget#%s QToolButton {"
        " background: transparent; color: %s; border: none;"
        " border-right: 1px solid %s; border-radius: 0; padding: 3px 8px; font-size: 11px; }"
        "QWidget#%s QToolButton:hover { background: %s; color: %s; }"
        "QWidget#%s QToolButton:checked { background: %s; color: %s; border-color: %s; }"
        "QWidget#%s QToolButton:disabled { color: %s; }"
        "QWidget#%s QToolButton:focus { border: %dpx solid %s; }"
        % (
            group,
            border,
            tokens.editor_bg,
            group,
            tokens.text_muted,
            border,
            group,
            tokens.tree_hover_bg,
            tokens.text_primary,
            group,
            tokens.tree_selected_bg,
            tokens.text_primary,
            border,
            group,
            faint,
            group,
            tokens.focus_border_width,
            tokens.accent,
        )
    )


__all__ = ["flat_tool_button_qss", "mode_group_qss"]
