"""Unit tests for shortcut preference helpers."""

from __future__ import annotations

import pytest

from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    close_tab_shortcut_id,
    default_shortcut_map,
    find_shortcut_conflicts,
    keep_preview_open_shortcut_id,
    parse_shortcut_overrides,
    project_tree_copy_shortcut_id,
    project_tree_delete_shortcut_id,
)

pytestmark = pytest.mark.unit


def test_default_shortcut_map_contains_known_command_ids() -> None:
    defaults = default_shortcut_map()
    assert defaults["shell.action.run.run"] == "F5"
    assert defaults["shell.action.run.debug"] == "Ctrl+F5"
    assert defaults["shell.action.run.runProject"] == "Shift+F5"
    assert defaults["shell.action.run.debugProject"] == "Ctrl+Shift+F5"
    assert defaults["shell.action.run.runWithArgs"] == "Ctrl+Shift+A"
    assert defaults["shell.action.run.stop"] == "Shift+F2"
    assert defaults["shell.action.run.restart"] == "Ctrl+Shift+F2"
    assert defaults["shell.action.edit.hoverInfo"] == "Ctrl+Shift+I"
    assert defaults["shell.action.file.newWindow"] == "Ctrl+Shift+N"
    assert defaults["shell.action.file.save"] == "Ctrl+S"
    assert defaults[close_tab_shortcut_id()] == "Ctrl+W"
    assert defaults[keep_preview_open_shortcut_id()] == "Ctrl+K, Enter"
    assert defaults[project_tree_copy_shortcut_id()] == "Ctrl+C"
    assert defaults[project_tree_delete_shortcut_id()] == "Delete"


def test_parse_shortcut_overrides_accepts_known_ids_and_discards_unknowns() -> None:
    parsed = parse_shortcut_overrides(
        {
            "keybindings": {
                "overrides": {
                    "shell.action.run.run": " Ctrl+R ",
                    "shell.action.unknown": "Ctrl+1",
                    "shell.action.file.save": 123,
                }
            }
        }
    )
    assert parsed == {"shell.action.run.run": "Ctrl+R"}


def test_build_effective_shortcut_map_applies_override_and_unbinds_empty() -> None:
    effective = build_effective_shortcut_map(
        {
            "shell.action.run.run": "Ctrl+R",
            "shell.action.file.save": "",
        }
    )
    assert effective["shell.action.run.run"] == "Ctrl+R"
    assert "shell.action.file.save" not in effective


def test_find_shortcut_conflicts_groups_action_ids_by_shortcut() -> None:
    conflicts = find_shortcut_conflicts(
        {
            "shell.action.file.save": "Ctrl+R",
            "shell.action.file.openProject": "Ctrl+R",
            "shell.action.run.run": "Ctrl+R",
        }
    )
    assert conflicts == {"Ctrl+R": ("shell.action.file.openProject", "shell.action.file.save")}


def test_find_shortcut_conflicts_ignores_cross_category_duplicates() -> None:
    conflicts = find_shortcut_conflicts(
        {
            "shell.action.edit.renameSymbol": "F2",
            "shell.shortcut.projectTree.rename": "F2",
        }
    )
    assert conflicts == {}


def test_no_duplicate_default_shortcuts() -> None:
    """Every non-empty default shortcut must be unique within each command category."""
    defaults = default_shortcut_map()
    conflicts = find_shortcut_conflicts(
        {action_id: shortcut for action_id, shortcut in defaults.items() if shortcut}
    )
    assert conflicts == {}, f"Duplicate default shortcuts: {conflicts}"
