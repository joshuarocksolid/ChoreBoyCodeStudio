"""Project-tree shortcut bindings and lookup helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.project.project_tree_widget import ProjectTreeWidget
from app.shell.shortcut_preferences import (
    project_tree_copy_shortcut_id,
    project_tree_cut_shortcut_id,
    project_tree_delete_shortcut_id,
    project_tree_paste_shortcut_id,
    project_tree_rename_shortcut_id,
)

PROJECT_TREE_SHORTCUT_SIGNALS: tuple[tuple[str, str], ...] = (
    (project_tree_delete_shortcut_id(), "deleteRequested"),
    (project_tree_rename_shortcut_id(), "renameRequested"),
    (project_tree_copy_shortcut_id(), "copyRequested"),
    (project_tree_cut_shortcut_id(), "cutRequested"),
    (project_tree_paste_shortcut_id(), "pasteRequested"),
)


def configure_project_tree_widget_shortcuts(
    tree: ProjectTreeWidget,
    resolver: Callable[[str], str],
) -> None:
    """Bind the project tree to the live effective-shortcut resolver."""
    tree.configure_shortcut_bindings(PROJECT_TREE_SHORTCUT_SIGNALS, resolver)


def configured_tree_shortcut(
    effective_shortcuts: Mapping[str, str],
    action_id: str,
) -> str | None:
    """Return the configured shortcut label for a tree action, if any."""
    shortcut = effective_shortcuts.get(action_id, "")
    return shortcut or None


def effective_shortcuts_for_window(window: Any) -> Mapping[str, str]:
    return window._effective_shortcuts
