"""Resolve Run / Debug shortcut labels from menu actions (Qt)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtGui import QKeySequence

from app.shell.run_target_summary import RunTargetSummaryShortcutLabels
from app.shell.shortcut_preferences import default_shortcut_map

if TYPE_CHECKING:
    from app.shell.menus import MenuStubRegistry


def resolve_run_target_shortcut_labels(registry: MenuStubRegistry | None) -> RunTargetSummaryShortcutLabels:
    """Read QAction shortcuts when present; fall back to default shortcut map."""
    defaults = default_shortcut_map()
    run_file = _shortcut_display(registry, "shell.action.run.run", defaults.get("shell.action.run.run", "F5"))
    debug_file = _shortcut_display(
        registry, "shell.action.run.debug", defaults.get("shell.action.run.debug", "Ctrl+F5")
    )
    run_project = _shortcut_display(
        registry, "shell.action.run.runProject", defaults.get("shell.action.run.runProject", "Shift+F5")
    )
    debug_project = _shortcut_display(
        registry,
        "shell.action.run.debugProject",
        defaults.get("shell.action.run.debugProject", "Ctrl+Shift+F5"),
    )
    return RunTargetSummaryShortcutLabels(
        run_file=run_file,
        debug_file=debug_file,
        run_project=run_project,
        debug_project=debug_project,
    )


def _shortcut_display(registry: MenuStubRegistry | None, action_id: str, fallback: str) -> str:
    if registry is None:
        return fallback
    action = registry.action(action_id)
    if action is None:
        return fallback
    seq = action.shortcut()
    if seq.isEmpty():
        return fallback
    return seq.toString(QKeySequence.NativeText)
