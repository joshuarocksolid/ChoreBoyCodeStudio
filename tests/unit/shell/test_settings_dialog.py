"""Unit tests for settings dialog interactions."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt
from PySide2.QtGui import QFont, QKeySequence
from PySide2.QtWidgets import QApplication, QDialogButtonBox, QHeaderView

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


def test_settings_dialog_shows_linter_scope_hint_when_global_differs_from_effective() -> None:
    global_snap = EditorSettingsSnapshot(selected_linter="default")
    project_snap = EditorSettingsSnapshot(selected_linter="pyflakes")
    dialog = SettingsDialog(
        global_snap,
        project_snapshot=project_snap,
        project_scope_available=True,
    )
    assert dialog._linter_provider_scope_hint is not None
    assert "differs from global" in dialog._linter_provider_scope_hint.text()


def test_settings_dialog_hides_linter_scope_hint_on_project_scope() -> None:
    global_snap = EditorSettingsSnapshot(selected_linter="default")
    project_snap = EditorSettingsSnapshot(selected_linter="pyflakes")
    dialog = SettingsDialog(
        global_snap,
        project_snapshot=project_snap,
        project_scope_available=True,
        initial_scope=SETTINGS_SCOPE_PROJECT,
    )
    assert dialog._linter_provider_scope_hint is not None
    assert dialog._linter_provider_scope_hint.isVisible() is False


def test_settings_dialog_no_linter_scope_hint_when_providers_match() -> None:
    snap = EditorSettingsSnapshot(selected_linter="pyflakes")
    dialog = SettingsDialog(snap, project_snapshot=snap, project_scope_available=True)
    assert dialog._linter_provider_scope_hint is None


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


def test_settings_dialog_snapshot_includes_organize_imports_on_save_toggle() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot(organize_imports_on_save=False))
    dialog._organize_imports_on_save_input.setChecked(True)

    snapshot = dialog.snapshot()
    assert snapshot.organize_imports_on_save is True


def test_settings_dialog_shows_python_tooling_status_labels() -> None:
    dialog = SettingsDialog(
        EditorSettingsSnapshot(),
        python_tooling_runtime_text="Black/isort/tomli: available",
        python_tooling_runtime_details="Vendor root: /tmp/vendor",
        python_tooling_config_text="Project pyproject.toml: detected",
        python_tooling_config_details="Path: /tmp/project/pyproject.toml",
    )

    assert dialog._python_tooling_runtime_status_label.text() == "Black/isort/tomli: available"
    assert dialog._python_tooling_runtime_status_label.toolTip() == "Vendor root: /tmp/vendor"
    assert dialog._python_tooling_config_status_label.text() == "Project pyproject.toml: detected"
    assert "/tmp/project/pyproject.toml" in dialog._python_tooling_config_status_label.toolTip()


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
    assert header.minimumSectionSize() < 100
    for col in (1, 2, 3):
        assert header.sectionResizeMode(col) == QHeaderView.Fixed

    table = dialog._syntax_color_table
    assert table.verticalHeader().minimumSectionSize() >= 28
    assert table.rowHeight(0) >= 28

    for token_key, line_edit in dialog._syntax_color_inputs.items():
        assert line_edit.maximumWidth() == 90, (
            f"Color input for '{token_key}' should have maximumWidth 90"
        )

    reset_btn = table.cellWidget(0, 3)
    pick_btn = table.cellWidget(0, 2)
    assert reset_btn is not None and pick_btn is not None
    assert table.columnWidth(3) >= reset_btn.sizeHint().width()
    assert table.columnWidth(2) >= pick_btn.sizeHint().width()


def test_settings_dialog_keybindings_reset_column_accommodates_reset_button() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    table = dialog._shortcut_table
    header = table.horizontalHeader()
    assert header.sectionResizeMode(3) == QHeaderView.Fixed
    reset_btn = table.cellWidget(0, 3)
    assert reset_btn is not None
    assert table.columnWidth(3) >= reset_btn.sizeHint().width()


def test_settings_dialog_linter_severity_combo_has_minimum_width_for_longest_label() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    first_code = next(iter(dialog._lint_severity_inputs))
    combo = dialog._lint_severity_inputs[first_code]
    assert combo.minimumContentsLength() >= len("WARNING")
    assert combo.minimumWidth() >= combo.sizeHint().width()
    assert dialog._linter_table.columnWidth(3) >= combo.sizeHint().width()


def test_settings_dialog_linter_reset_button_respects_size_hint_width() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    reset_btn = dialog._linter_table.cellWidget(0, 4)
    assert reset_btn is not None
    assert reset_btn.minimumWidth() >= reset_btn.sizeHint().width()


def test_settings_dialog_footer_buttons_clear_standard_icons() -> None:
    dialog = SettingsDialog(EditorSettingsSnapshot())
    assert dialog._ok_button is not None
    assert dialog._ok_button.icon().isNull()
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    cancel_btn = button_box.button(QDialogButtonBox.Cancel)
    assert cancel_btn is not None
    assert cancel_btn.icon().isNull()
