"""Unit tests for settings dialog interactions."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QApplication

from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import EditorSettingsSnapshot

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_settings_dialog_snapshot_includes_shortcut_overrides() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    run_editor = dialog._shortcut_editors["shell.action.run.run"]
    run_editor.setKeySequence(QKeySequence("Ctrl+R"))

    snapshot = dialog.snapshot()
    assert snapshot.shortcut_overrides["shell.action.run.run"] == "Ctrl+R"


def test_settings_dialog_detects_conflicting_shortcuts_and_disables_ok() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    run_editor = dialog._shortcut_editors["shell.action.run.run"]
    save_editor = dialog._shortcut_editors["shell.action.file.save"]
    run_editor.setKeySequence(QKeySequence("Ctrl+R"))
    save_editor.setKeySequence(QKeySequence("Ctrl+R"))
    dialog._refresh_shortcut_conflicts()

    assert dialog._ok_button is not None
    assert dialog._ok_button.isEnabled() is False


def test_settings_dialog_snapshot_includes_syntax_color_overrides() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    keyword_input = dialog._syntax_color_inputs["keyword"]
    keyword_input.setText("#112233")
    dialog._handle_syntax_color_text_edited("keyword")

    snapshot = dialog.snapshot()
    assert snapshot.syntax_color_overrides_light["keyword"] == "#112233"


def test_settings_dialog_invalid_syntax_color_disables_ok() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    keyword_input = dialog._syntax_color_inputs["keyword"]
    keyword_input.setText("bad-color")
    dialog._handle_syntax_color_text_edited("keyword")

    assert dialog._ok_button is not None
    assert dialog._ok_button.isEnabled() is False


def test_settings_dialog_snapshot_includes_lint_rule_overrides() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    py220_checkbox = dialog._lint_enabled_inputs["PY220"]
    py220_checkbox.setChecked(False)

    snapshot = dialog.snapshot()
    assert snapshot.lint_rule_overrides["PY220"]["enabled"] is False


def test_settings_dialog_reset_all_keybindings_restores_defaults() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    run_editor = dialog._shortcut_editors["shell.action.run.run"]
    run_editor.setKeySequence(QKeySequence("Ctrl+R"))

    dialog._handle_reset_all_shortcuts()
    snapshot = dialog.snapshot()
    assert snapshot.shortcut_overrides == {}
