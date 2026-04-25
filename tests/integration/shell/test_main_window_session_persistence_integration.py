"""Integration tests for project session save/restore in MainWindow."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCursor

from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication
    import PySide2.QtGui as qt_gui
    import PySide2.QtWidgets as qt_widgets

    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _set_cursor_position(editor_widget, *, line: int, column: int) -> None:  # type: ignore[no-untyped-def]
    cursor = editor_widget.textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, max(0, line - 1))
    cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, max(0, column - 1))
    editor_widget.setTextCursor(cursor)


def test_main_window_restores_saved_project_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Session Restore")
    file_one = project_root / "alpha.py"
    file_one.write_text("line1\nline2\nline3\nline4\nline5\nline6\n", encoding="utf-8")
    file_two = project_root / "beta.py"
    file_two.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    file_one_path = str(file_one.resolve())
    file_two_path = str(file_two.resolve())
    assert window._open_file_in_editor(file_one_path) is True
    assert window._open_file_in_editor(file_two_path) is True

    first_widget = window._editor_widgets_by_path[file_one_path]
    second_widget = window._editor_widgets_by_path[file_two_path]
    _set_cursor_position(first_widget, line=4, column=3)
    _set_cursor_position(second_widget, line=2, column=2)

    first_index = window._tab_index_for_path(file_one_path)
    assert first_index >= 0
    assert window._editor_tabs_widget is not None
    window._editor_tabs_widget.setCurrentIndex(first_index)
    window._breakpoints_by_file[file_one_path] = {2, 5}
    window._breakpoints_by_file[file_two_path] = {3}

    window._local_history_workflow.persist_session_state()
    window._reset_editor_tabs()
    window._breakpoints_by_file.clear()
    window._local_history_workflow.restore_session_state(str(project_root.resolve()))
    app.processEvents()

    assert window._editor_manager.open_paths() == [file_one_path, file_two_path]
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.file_path == file_one_path
    assert window._breakpoints_by_file[file_one_path] == {2, 5}
    assert window._breakpoints_by_file[file_two_path] == {3}

    restored_first_widget = window._editor_widgets_by_path[file_one_path]
    restored_second_widget = window._editor_widgets_by_path[file_two_path]
    assert restored_first_widget.textCursor().blockNumber() + 1 == 4
    assert restored_first_widget.textCursor().positionInBlock() + 1 == 3
    assert restored_second_widget.textCursor().blockNumber() + 1 == 2
    assert restored_second_widget.textCursor().positionInBlock() + 1 == 2
    window.close()


def test_opening_second_project_persists_and_restores_first_project_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Switching projects should persist first-session state and restore it when reopened."""
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_one = tmp_path / "project_one"
    create_blank_project(str(project_one.resolve()), project_name="Project One")
    project_one_file = project_one / "first.py"
    project_one_file.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    project_two = tmp_path / "project_two"
    create_blank_project(str(project_two.resolve()), project_name="Project Two")
    project_two_file = project_two / "second.py"
    project_two_file.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)

    assert window._open_project_by_path(str(project_one.resolve())) is True
    project_one_path = str(project_one_file.resolve())
    assert window._open_file_in_editor(project_one_path) is True
    widget_one = window._editor_widgets_by_path[project_one_path]
    _set_cursor_position(widget_one, line=3, column=2)
    window._breakpoints_by_file[project_one_path] = {2}

    # Opening another project should persist current project-one session state.
    assert window._open_project_by_path(str(project_two.resolve())) is True
    project_two_path = str(project_two_file.resolve())
    assert window._open_file_in_editor(project_two_path) is True

    # Reopen project one and verify its previous editor state is restored.
    assert window._open_project_by_path(str(project_one.resolve())) is True
    app.processEvents()
    assert project_one_path in window._editor_widgets_by_path
    restored_widget = window._editor_widgets_by_path[project_one_path]
    assert restored_widget.textCursor().blockNumber() + 1 == 3
    assert restored_widget.textCursor().positionInBlock() + 1 == 2
    assert window._breakpoints_by_file[project_one_path] == {2}
    window.close()
