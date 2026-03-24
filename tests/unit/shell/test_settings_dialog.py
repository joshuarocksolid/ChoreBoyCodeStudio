"""Unit tests for settings dialog interactions."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt
from PySide2.QtGui import QFont, QKeySequence
from PySide2.QtWidgets import QApplication

from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import EditorSettingsSnapshot, SETTINGS_SCOPE_PROJECT

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


def test_settings_dialog_snapshot_includes_selected_linter() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    dialog._linter_provider_input.setCurrentIndex(1)

    snapshot = dialog.snapshot()
    assert snapshot.selected_linter == "pyflakes"


def test_settings_dialog_linter_toggle_controls_provider_and_rules() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    dialog._linter_enabled_input.setChecked(False)

    assert dialog._linter_provider_input.isEnabled() is False
    assert dialog._linter_table.isEnabled() is False


def test_settings_dialog_reset_all_keybindings_restores_defaults() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    run_editor = dialog._shortcut_editors["shell.action.run.run"]
    run_editor.setKeySequence(QKeySequence("Ctrl+R"))

    dialog._handle_reset_all_shortcuts()
    snapshot = dialog.snapshot()
    assert snapshot.shortcut_overrides == {}


def test_settings_dialog_disables_project_scope_without_project_snapshot() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    assert dialog._project_scope_available is False
    assert dialog._scope_input is not None
    assert dialog._scope_input.selected_data() != SETTINGS_SCOPE_PROJECT


def test_settings_dialog_project_scope_hides_global_only_controls() -> None:
    global_snapshot = EditorSettingsSnapshot(
        tab_width=4,
        auto_open_console_on_run_output=True,
        file_exclude_patterns=["__pycache__", ".git"],
    )
    project_snapshot = EditorSettingsSnapshot(
        tab_width=2,
        auto_open_console_on_run_output=False,
        file_exclude_patterns=["__pycache__", ".git", "*.tmp"],
    )
    dialog = SettingsDialog(
        global_snapshot,
        project_snapshot=project_snapshot,
        project_scope_available=True,
        initial_scope=SETTINGS_SCOPE_PROJECT,
    )

    assert dialog.selected_scope == SETTINGS_SCOPE_PROJECT
    assert dialog._appearance_group is not None
    assert dialog._appearance_group.isVisible() is False
    assert dialog._scope_banner_label is not None
    assert "Project overrides apply to this project only" in dialog._scope_banner_label.text()

    dialog._handle_reset_output_group_to_global()
    dialog._handle_reset_editor_group_to_global()
    snapshot = dialog.snapshot()
    assert snapshot.tab_width == global_snapshot.tab_width
    assert (
        snapshot.auto_open_console_on_run_output
        == global_snapshot.auto_open_console_on_run_output
    )


def test_settings_dialog_snapshot_includes_enable_preview_toggle() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot(enable_preview=True))
    dialog._enable_preview_input.setChecked(False)

    snapshot = dialog.snapshot()
    assert snapshot.enable_preview is False


def test_settings_dialog_tab_bar_prevents_label_clipping() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    tab_bar = dialog._tabs_widget.tabBar()

    assert tab_bar.elideMode() == Qt.ElideNone
    assert tab_bar.expanding() is False

    font = tab_bar.font()
    assert font.pixelSize() == 12
    assert font.weight() >= QFont.DemiBold


def test_settings_dialog_syntax_color_table_width_constraints() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    header = dialog._syntax_color_table.horizontalHeader()
    assert header.minimumSectionSize() >= 200

    for token_key, line_edit in dialog._syntax_color_inputs.items():
        assert line_edit.maximumWidth() == 90, (
            f"Color input for '{token_key}' should have maximumWidth 90"
        )
