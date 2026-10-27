"""Form keys against the shell shortcut table (UX-KEY-001..004)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.layout_actions import request_for
from app.features.form_builder.engine.shell_commands import (
    FORM_COMMANDS,
    FORM_SHORTCUT_CATEGORY,
    INERT_SHORTCUTS,
    INERT_STATUS,
    contexts_overlap,
    menu_commands,
    registered_commands,
    shell_command_contexts,
    shortcut_collisions,
    shortcut_rows,
)
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS

pytestmark = pytest.mark.unit

# Keys from UX-KEY-004. A row that disappears fails this list before the
# collision function can hide it.
_SPEC_KEYS = (
    "Ctrl+S",
    "Ctrl+Shift+S",
    "Ctrl+W",
    "Ctrl+Z",
    "Ctrl+Shift+Z",
    "Ctrl+X",
    "Ctrl+C",
    "Ctrl+V",
    "Delete",
    "Backspace",
    "Ctrl+A",
    "Ctrl+D",
    "Ctrl+F",
    "Ctrl+R",
    "F2",
    "Return",
    "Esc",
    "Tab",
    "Shift+Tab",
    "Up",
    "Down",
    "Left",
    "Right",
    "Shift+Up",
    "Alt+Up",
    "Alt+Left",
    "Alt+Shift+Up",
    "Ctrl+Shift+Up",
    "/",
    "Ctrl+1",
    "Ctrl+2",
    "Ctrl+3",
    "Ctrl+4",
    "Ctrl+5",
    "Ctrl+6",
    "Ctrl+J",
    "Ctrl+Shift+G",
    "Ctrl+Shift+B",
    "Ctrl+=",
    "Ctrl+-",
    "Ctrl+0",
    "Ctrl+9",
    "Ctrl+Shift+V",
    "Ctrl+Shift+R",
    "F5",
    "Shift+F5",
    "Ctrl+F5",
    "Ctrl+Shift+F5",
    "F3",
    "F7",
    "F8",
    "F4",
    "Alt+1",
    "Alt+4",
    "Shift+F10",
    "Menu",
    "Ctrl+K, W",
    "Shift+F2",
    "Ctrl+Shift+F",
)


def _shell_map() -> dict[str, str]:
    return {command.action_id: command.default_shortcut for command in SHORTCUT_COMMANDS}


def test_form_table_does_not_collide_with_the_shell_table() -> None:
    problems = shortcut_collisions(_shell_map())
    assert problems == ()


def test_planted_shell_duplicate_is_reported() -> None:
    planted = _shell_map()
    planted["shell.action.edit.find"] = "Ctrl+9"
    problems = shortcut_collisions(planted)
    assert any("zoomToFit" in problem and "Ctrl+9" in problem for problem in problems)


def test_layout_keys_do_not_overlap_editor_group_focus() -> None:
    focus = shell_command_contexts("shell.action.view.focusFirstEditorGroup")
    horizontal = next(command for command in FORM_COMMANDS if command.shortcut == "Ctrl+1")
    assert not contexts_overlap(horizontal.contexts, focus)


def test_inert_keys_are_reserved_and_not_registered() -> None:
    registered = {command.shortcut for command in registered_commands()}
    for key in INERT_SHORTCUTS:
        assert key not in registered
    assert INERT_STATUS == "Not used in the form designer."


def test_registered_rows_use_portable_ctrl_text_and_the_form_category() -> None:
    assert shortcut_rows()
    for action_id, _label, shortcut, category in shortcut_rows():
        assert category == FORM_SHORTCUT_CATEGORY
        assert action_id.startswith("form.action.")
        assert "Meta" not in shortcut
        assert "Cmd" not in shortcut
        assert "Ctrl" in shortcut or shortcut[:1].isupper() or shortcut in {"/", "Tab", "Esc", "Return", "Menu"}


def test_new_keys_stay_disabled_until_a_handler_exists() -> None:
    live = {"form.action.zoomToFit", "form.action.editText"}
    for command in registered_commands():
        handled = command.command_id in live or request_for(command.command_id) is not None
        assert command.available is handled


def test_spec_keys_are_in_the_table() -> None:
    present = {command.shortcut for command in FORM_COMMANDS if command.shortcut}
    present.update(INERT_SHORTCUTS)
    missing = [key for key in _SPEC_KEYS if key not in present]
    assert missing == []


def test_shell_rows_match_the_shell_shortcut() -> None:
    shell = _shell_map()
    for command in FORM_COMMANDS:
        if command.kind != "shell" or not command.shell_action_id:
            continue
        assert shell[command.shell_action_id] == command.shortcut


def test_menu_labels_do_not_name_milestones() -> None:
    for command in menu_commands():
        label = " ".join(command.menu_path)
        assert "M2" not in label
        assert "M3" not in label
        assert "M5" not in label
        assert "M6" not in label


def test_one_binding_per_alt_arrow() -> None:
    alt_up = [command for command in registered_commands() if command.shortcut == "Alt+Up"]
    assert len(alt_up) == 1
