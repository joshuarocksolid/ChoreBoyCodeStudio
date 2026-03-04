"""Unit tests for dynamic shortcuts help content."""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.shell.main_window import MainWindow
from app.shell.shortcut_preferences import build_effective_shortcut_map

pytestmark = pytest.mark.unit


def test_build_shortcuts_help_markdown_uses_effective_shortcuts() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._effective_shortcuts = build_effective_shortcut_map(
        {"shell.action.run.run": "Ctrl+R"}
    )

    markdown = MainWindow._build_shortcuts_help_markdown(window)

    assert "# Keyboard Shortcuts" in markdown
    assert "**Ctrl+R**: Run" in markdown
    assert "_Customize shortcuts in **File > Settings > Keybindings**._" in markdown


def test_build_shortcuts_help_markdown_hides_unbound_commands() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._effective_shortcuts = build_effective_shortcut_map(
        {"shell.action.file.save": ""}
    )

    markdown = MainWindow._build_shortcuts_help_markdown(window)

    assert "**Ctrl+S**: Save" not in markdown
