"""Integration tests for global history restore workflows."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QDialog

from app.project.project_service import create_blank_project
from app.shell.history_restore_picker import HISTORY_RESTORE_ACTION_RESTORE_LATEST
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


def _wait_for(predicate, app, *, timeout_seconds: float = 1.5) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def test_global_history_restore_reopens_deleted_file_into_dirty_buffer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Global History Project")
    file_path = project_root / "deleted.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    monkeypatch.setattr(window, "_apply_detected_indentation_for_widget", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window, "_handle_editor_tab_changed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window, "_refresh_save_action_states", lambda: None)
    monkeypatch.setattr(window, "_update_editor_status_for_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window, "_render_lint_diagnostics_for_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window._local_history_workflow, "schedule_autosave", lambda *_args, **_kwargs: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._loaded_project is not None

    window._local_history_workflow.local_history_store.create_checkpoint(
        str(file_path.resolve()),
        "print('recovered')\n",
        project_id=window._loaded_project.metadata.project_id,
        project_root=window._loaded_project.project_root,
        source="save",
        label="Recovered Revision",
    )
    file_path.unlink()
    window._local_history_workflow.local_history_store.record_deleted_path(
        project_id=window._loaded_project.metadata.project_id,
        project_root=window._loaded_project.project_root,
        deleted_path=str(file_path.resolve()),
    )

    def fake_exec(self) -> int:  # type: ignore[no-untyped-def]
        assert self._results.topLevelItemCount() == 1
        assert self._results.topLevelItem(0).text(1) == "Deleted"
        self._results.setCurrentItem(self._results.topLevelItem(0))
        self._requested_action = HISTORY_RESTORE_ACTION_RESTORE_LATEST
        return QDialog.Accepted

    monkeypatch.setattr("app.shell.history_restore_picker.HistoryRestorePickerDialog.exec_", fake_exec)

    window._local_history_workflow.open_global_history()
    assert _wait_for(
        lambda: window._editor_manager.get_tab(str(file_path.resolve())) is not None,
        app,
    )

    restored_tab = window._editor_manager.get_tab(str(file_path.resolve()))
    assert restored_tab is not None
    assert restored_tab.current_content == "print('recovered')\n"
    assert restored_tab.is_dirty is True
    assert file_path.exists() is False
    _dispose_window(window, app)
