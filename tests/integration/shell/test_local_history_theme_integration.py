"""Integration checks for local history dialogs under light and dark themes."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QDialog

from app.core import constants
from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def _dispose_window(window: MainWindow, app) -> None:  # type: ignore[no-untyped-def]
    window._is_shutting_down = True
    window._begin_shutdown_teardown()
    window._stop_active_run_before_close()
    window.deleteLater()
    app.processEvents()


def _wait_for(predicate, app, *, timeout_seconds: float = 2.0) -> bool:  # type: ignore[no-untyped-def]
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def test_local_history_dialogs_open_under_light_and_dark_themes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Theme History Project")
    file_path = project_root / "main.py"
    file_path.write_text("print('current')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._loaded_project is not None

    window._local_history_workflow.local_history_store.create_checkpoint(
        str(file_path.resolve()),
        "print('saved')\n",
        project_id=window._loaded_project.metadata.project_id,
        project_root=window._loaded_project.project_root,
        source="save",
        label="Saved Revision",
    )

    opened_history_dialogs: list[object] = []

    def fake_local_history_exec(dialog) -> int:  # type: ignore[no-untyped-def]
        opened_history_dialogs.append(dialog)
        return QDialog.Rejected

    def fake_history_restore_exec(dialog) -> int:  # type: ignore[no-untyped-def]
        return QDialog.Rejected

    monkeypatch.setattr("app.shell.local_history_dialog.LocalHistoryDialog.exec_", fake_local_history_exec)
    monkeypatch.setattr("app.shell.history_restore_picker.HistoryRestorePickerDialog.exec_", fake_history_restore_exec)

    for mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK):
        window._handle_set_theme(mode)
        window._local_history_workflow.show_local_history_for_path(str(file_path.resolve()))
        window._local_history_workflow.open_global_history()
        assert _wait_for(lambda: window._local_history_workflow.history_restore_picker_dialog is not None, app)

        picker_dialog = window._local_history_workflow.history_restore_picker_dialog
        assert picker_dialog is not None
        assert picker_dialog._results.topLevelItemCount() == 1
        assert picker_dialog._search_input is not None

    assert len(opened_history_dialogs) == 2
    _dispose_window(window, app)
