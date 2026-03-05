"""Unit tests for shortcut preference helpers."""

from __future__ import annotations

import pytest

from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    close_tab_shortcut_id,
    default_shortcut_map,
    find_shortcut_conflicts,
    parse_shortcut_overrides,
)

pytestmark = pytest.mark.unit


def test_default_shortcut_map_contains_known_command_ids() -> None:
    defaults = default_shortcut_map()
    assert defaults["designer.file.new_form"] == "Ctrl+Shift+N"
    assert defaults["designer.layout.horizontal"] == "Ctrl+1"
    assert defaults["designer.layout.vertical"] == "Ctrl+2"
    assert defaults["designer.layout.grid"] == "Ctrl+3"
    assert defaults["designer.layout.break"] == "Ctrl+0"
    assert defaults["designer.form.preview"] == "Ctrl+R"
    assert defaults["designer.form.check_compat"] == "Ctrl+Shift+R"
    assert defaults["designer.form.add_resource"] == ""
    assert defaults["designer.mode.widget"] == "F3"
    assert defaults["designer.mode.signals_slots"] == "F4"
    assert defaults["designer.mode.buddy"] == "F5"
    assert defaults["designer.mode.tab_order"] == "F6"
    assert defaults["shell.action.run.run"] == "F5"
    assert defaults["shell.action.file.save"] == "Ctrl+S"
    assert defaults[close_tab_shortcut_id()] == "Ctrl+W"


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
            "shell.action.run.run": "Ctrl+R",
            "shell.action.file.save": "Ctrl+R",
            "shell.action.file.openProject": "Ctrl+O",
        }
    )
    assert conflicts == {"Ctrl+R": ("shell.action.file.save", "shell.action.run.run")}
