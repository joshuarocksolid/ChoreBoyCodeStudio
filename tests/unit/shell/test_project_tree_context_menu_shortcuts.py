"""Unit tests for project-tree context menu shortcut labels."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.shell.project_tree_context_menu import _tree_menu_shortcuts
from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    project_tree_copy_shortcut_id,
    project_tree_delete_shortcut_id,
)

pytestmark = pytest.mark.unit


def test_tree_menu_shortcuts_reflect_effective_shortcut_overrides() -> None:
    effective = build_effective_shortcut_map(
        {
            project_tree_copy_shortcut_id(): "Ctrl+Shift+C",
            project_tree_delete_shortcut_id(): "Shift+Delete",
        }
    )
    window = SimpleNamespace(_effective_shortcuts=effective)

    shortcuts = _tree_menu_shortcuts(window)

    assert shortcuts["copy"] == "Ctrl+Shift+C"
    assert shortcuts["delete"] == "Shift+Delete"
