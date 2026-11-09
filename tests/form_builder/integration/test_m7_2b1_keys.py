# pyright: reportAttributeAccessIssue=false
"""Formula keys are listed for the key table and do not collide."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration import keys_ext
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS

pytestmark = pytest.mark.unit


def test_formula_keys_are_listed_beside_the_table() -> None:
    rows = {row.command_id: row for row in keys_ext.default_registry().commands()}
    field = {
        "form.action.commitFormula": ("Commit formula", "Ctrl+Enter"),
        "form.action.cancelFormula": ("Cancel formula", "Esc"),
        "form.action.completeFormula": ("Complete", "Ctrl+Space"),
        "form.action.applyFormulaFix": ("Apply formula fix", "Ctrl+."),
    }
    for command_id, (label, shortcut) in field.items():
        row = rows[command_id]
        assert row.label == label and row.shortcut == shortcut
        assert row.contexts == ("formula_field",) and row.kind == "qt" and row.available
    edit = rows["form.action.editStateRow"]
    assert edit.label == "Edit the State row" and edit.shortcut == "Enter"
    assert edit.contexts == ("state_list",) and edit.kind == "qt"
    shell = {command.action_id: command.default_shortcut for command in SHORTCUT_COMMANDS}
    assert keys_ext.collisions(shell) == ()
