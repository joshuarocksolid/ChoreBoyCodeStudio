"""Unit tests for dynamic shortcuts help content."""

from __future__ import annotations

import pytest

from app.shell.help_controller import ShellHelpController
from app.shell.shortcut_preferences import build_effective_shortcut_map

pytestmark = pytest.mark.unit


def test_build_shortcuts_help_markdown_uses_effective_shortcuts() -> None:
    controller = ShellHelpController(
        state_root=None,
        resolve_theme_tokens=lambda: object(),
        reveal_path_in_file_manager=lambda _path: None,
        get_effective_shortcuts=lambda: build_effective_shortcut_map(
            {"shell.action.run.run": "Ctrl+R"}
        ),
    )

    markdown = controller.build_shortcuts_help_markdown()

    assert "# Keyboard Shortcuts" in markdown
    assert "**Ctrl+R**: Run" in markdown
    assert "_Customize shortcuts in **File > Settings > Keybindings**._" in markdown


def test_build_shortcuts_help_markdown_hides_unbound_commands() -> None:
    controller = ShellHelpController(
        state_root=None,
        resolve_theme_tokens=lambda: object(),
        reveal_path_in_file_manager=lambda _path: None,
        get_effective_shortcuts=lambda: build_effective_shortcut_map(
            {"shell.action.file.save": ""}
        ),
    )

    markdown = controller.build_shortcuts_help_markdown()

    assert "**Ctrl+S**: Save" not in markdown
