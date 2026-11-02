"""Theme helpers for Team Sync surfaces. Colors come from ShellThemeTokens."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def focus_rule(tokens: ShellThemeTokens, selector: str) -> str:
    return (
        f"{selector}:focus {{ border: {tokens.focus_border_width}px solid {tokens.accent}; }}"
    )


def surface_qss(tokens: ShellThemeTokens) -> str:
    return (
        f"background: {tokens.panel_bg}; color: {tokens.text_primary};"
        f" font-size: 13px;"
    )


def muted_qss(tokens: ShellThemeTokens) -> str:
    return f"color: {tokens.text_muted}; background: transparent;"


def field_qss(tokens: ShellThemeTokens) -> str:
    return (
        f"background: {tokens.input_bg}; color: {tokens.text_primary};"
        f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 4px 8px;"
        f" selection-background-color: {tokens.accent};"
    )


def button_qss(tokens: ShellThemeTokens) -> str:
    return (
        "QPushButton {"
        f" background: {tokens.input_bg}; color: {tokens.text_primary};"
        f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 4px 10px;"
        "}"
        "QPushButton:disabled { color: " + tokens.text_muted + "; }"
        + focus_rule(tokens, "QPushButton")
    )


def primary_button_qss(tokens: ShellThemeTokens) -> str:
    fg = tokens.toolbar_package_fg or "#FFFFFF"
    return (
        "QPushButton {"
        f" background: {tokens.toolbar_package_bg or tokens.accent}; color: {fg};"
        f" border: none; border-radius: 4px; padding: 4px 12px; font-weight: 600;"
        "}"
        "QPushButton:disabled { background: " + tokens.border + "; color: " + tokens.text_muted + "; }"
        + focus_rule(tokens, "QPushButton")
    )


def incoming_qss(tokens: ShellThemeTokens) -> str:
    return (
        f"background: {tokens.row_alt_bg or tokens.editor_bg};"
        f" border: 1px solid {tokens.border}; border-radius: 6px;"
    )


def level_color(tokens: ShellThemeTokens, level: str) -> str:
    if level == "warn":
        return tokens.diag_warning_color or "#B45309"
    if level == "ok":
        return tokens.test_passed_color or "#1A7F37"
    return tokens.diag_info_color or tokens.accent


__all__ = [
    "button_qss",
    "field_qss",
    "focus_rule",
    "incoming_qss",
    "level_color",
    "muted_qss",
    "primary_button_qss",
    "surface_qss",
]
