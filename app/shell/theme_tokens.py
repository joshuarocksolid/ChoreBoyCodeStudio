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


def tokens_from_palette(palette: QPalette, *, prefer_dark: bool = False) -> ShellThemeTokens:
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
        )
    return ShellThemeTokens(
        window_bg="#F8F9FA",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#212529",
        text_muted="#6C757D",
        border="#DEE2E6",
        accent="#3366FF",
    )


def to_qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)
