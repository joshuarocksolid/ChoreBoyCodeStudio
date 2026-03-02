"""Theme token derivation utilities for shell styling."""

from __future__ import annotations

from dataclasses import dataclass

from PySide2.QtGui import QColor, QPalette


@dataclass(frozen=True)
class ShellThemeTokens:
    window_bg: str
    panel_bg: str
    editor_bg: str
    text_primary: str
    text_muted: str
    border: str
    accent: str
    gutter_bg: str
    gutter_text: str
    line_highlight: str
    is_dark: bool = False
    tree_hover_bg: str = ""
    tree_selected_bg: str = ""
    icon_primary: str = ""
    icon_muted: str = ""


def tokens_from_palette(
    palette: QPalette,
    *,
    prefer_dark: bool = False,
    force_mode: str | None = None,
) -> ShellThemeTokens:
    """Derive theme tokens.

    ``force_mode`` accepts ``"light"``, ``"dark"``, or ``None``.  When set it
    overrides both ``prefer_dark`` and the palette lightness heuristic.
    """
    if force_mode == "dark":
        is_dark = True
    elif force_mode == "light":
        is_dark = False
    else:
        window_color = palette.color(QPalette.Window)
        is_dark = prefer_dark or window_color.lightness() < 128
    if is_dark:
        return ShellThemeTokens(
            window_bg="#1F2428",
            panel_bg="#262C33",
            editor_bg="#1B1F23",
            text_primary="#E9ECEF",
            text_muted="#ADB5BD",
            border="#3C434A",
            accent="#5B8CFF",
            gutter_bg="#1F2428",
            gutter_text="#6C757D",
            line_highlight="#252B33",
            is_dark=True,
            tree_hover_bg="#2A3038",
            tree_selected_bg="#2D3A4A",
            icon_primary="#CED4DA",
            icon_muted="#5B8CFF",
        )
    return ShellThemeTokens(
        window_bg="#F8F9FA",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#212529",
        text_muted="#6C757D",
        border="#DEE2E6",
        accent="#3366FF",
        gutter_bg="#F1F3F5",
        gutter_text="#ADB5BD",
        line_highlight="#EEF7FF",
        is_dark=False,
        tree_hover_bg="#E9ECEF",
        tree_selected_bg="#D0E2FF",
        icon_primary="#495057",
        icon_muted="#3366FF",
    )


def to_qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)
