"""Theme helpers for Team Sync surfaces. Colors come from ShellThemeTokens."""

from __future__ import annotations

from app.qt.QtGui import QColor
from app.shell.theme_tokens import ShellThemeTokens


def blend(base: str, tint: str, amount: float) -> str:
    """Mix ``tint`` into ``base``. ``amount`` 0 keeps ``base``."""
    start = QColor(base)
    other = QColor(tint)
    if not start.isValid():
        start = QColor("#FFFFFF")
    if not other.isValid():
        other = start
    ratio = max(0.0, min(1.0, amount))

    def channel(left: int, right: int) -> int:
        return max(0, min(255, int(round(left + (right - left) * ratio))))

    return "#{:02X}{:02X}{:02X}".format(
        channel(start.red(), other.red()),
        channel(start.green(), other.green()),
        channel(start.blue(), other.blue()),
    )


def accent_soft(tokens: ShellThemeTokens) -> str:
    return blend(tokens.panel_bg or tokens.editor_bg, tokens.accent, 0.14)


def warning_soft(tokens: ShellThemeTokens) -> str:
    return blend(tokens.panel_bg or tokens.editor_bg, tokens.diag_warning_color or "#D97706", 0.18)


def mine_bg(tokens: ShellThemeTokens) -> str:
    return blend(tokens.editor_bg or tokens.panel_bg, tokens.diag_warning_color or "#D97706", 0.22)


def theirs_bg(tokens: ShellThemeTokens) -> str:
    return blend(tokens.editor_bg or tokens.panel_bg, "#0F766E", 0.20)


def added_soft(tokens: ShellThemeTokens) -> str:
    return blend(tokens.editor_bg or tokens.panel_bg, tokens.test_passed_color or "#1A7F37", 0.18)


def removed_soft(tokens: ShellThemeTokens) -> str:
    return blend(tokens.editor_bg or tokens.panel_bg, tokens.diag_error_color or "#E03131", 0.18)


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
    return (
        "QPushButton {"
        f" background: {tokens.accent}; color: #FFFFFF;"
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
    "accent_soft",
    "added_soft",
    "blend",
    "button_qss",
    "field_qss",
    "focus_rule",
    "incoming_qss",
    "level_color",
    "mine_bg",
    "muted_qss",
    "primary_button_qss",
    "removed_soft",
    "surface_qss",
    "theirs_bg",
    "warning_soft",
]
