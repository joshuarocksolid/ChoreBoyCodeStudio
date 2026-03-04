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
