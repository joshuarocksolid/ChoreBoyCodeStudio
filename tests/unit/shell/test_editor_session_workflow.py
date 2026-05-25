"""Unit tests for editor session persist/restore workflow."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCursor  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.editor_manager import EditorManager  # noqa: E402
from app.shell.breakpoint_store import BreakpointStore  # noqa: E402
from app.shell.editor_session_workflow import EditorSessionWorkflow  # noqa: E402

pytestmark = pytest.mark.unit


def _loaded_project(project_root: Path) -> object:
    return SimpleNamespace(
        project_root=str(project_root.resolve()),
        metadata=SimpleNamespace(project_id="proj_demo"),
    )


def test_project_session_persist_and_restore_round_trips_editor_state(
    tmp_path: Path,
    qapp,  # type: ignore[no-untyped-def]
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    file_path_str = str(file_path.resolve())

    manager = EditorManager()
    manager.open_file(file_path_str)
    widgets: dict[str, CodeEditorWidget] = {file_path_str: CodeEditorWidget()}
    widgets[file_path_str].setPlainText("one\ntwo\nthree\n")
    cursor = widgets[file_path_str].textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, 1)
    cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 1)
    widgets[file_path_str].setTextCursor(cursor)

    breakpoint_store = BreakpointStore()
    breakpoint_store.set_line_enabled(file_path_str, 2, enabled=True)
    selected_tabs: list[int] = []
    open_file_handlers = {"handler": lambda _path: True}
    workflow = EditorSessionWorkflow(
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda path: widgets.get(path),
        open_file_in_editor=lambda path: open_file_handlers["handler"](path),
        tab_index_for_path=lambda path: 0 if path == file_path_str else -1,
        set_current_tab_index=selected_tabs.append,
        logger=logging.getLogger("test.editor_session_workflow"),
        breakpoint_store=breakpoint_store,
    )

    workflow.persist_session_state(project_root=str(project_root.resolve()))

    restored_manager = EditorManager()
    restored_widgets: dict[str, CodeEditorWidget] = {}

    def open_restored_file(path: str) -> bool:
        opened = restored_manager.open_file(path)
        restored_widget = CodeEditorWidget()
        restored_widget.setPlainText(opened.tab.current_content)
        restored_widgets[path] = restored_widget
        widgets.clear()
        widgets.update(restored_widgets)
        return True

    workflow.set_editor_manager(restored_manager)
    breakpoint_store.clear_all()
    open_file_handlers["handler"] = open_restored_file
    workflow.restore_session_state(str(project_root.resolve()))

    assert restored_manager.open_paths() == [file_path_str]
    assert breakpoint_store.lines_for_file(file_path_str) == {2}
    assert breakpoint_store.get_spec(file_path_str, 2) is not None
    assert selected_tabs == [0]
    restored_cursor = restored_widgets[file_path_str].textCursor()
    assert restored_cursor.blockNumber() + 1 == 2
    assert restored_cursor.positionInBlock() + 1 == 2


def test_local_history_workflow_delegates_session_to_editor_session_module(
    tmp_path: Path,
    qapp,  # type: ignore[no-untyped-def]
) -> None:
    from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
    from app.shell.local_history_workflow import LocalHistoryWorkflow  # noqa: E402

    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("hello\n", encoding="utf-8")
    file_path_str = str(file_path.resolve())
    manager = EditorManager()
    manager.open_file(file_path_str)
    widget = CodeEditorWidget()
    widget.setPlainText("hello\n")

    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=SimpleNamespace(
            delete_draft=lambda *_args, **_kwargs: None,
            load_draft=lambda *_args, **_kwargs: None,
            save_draft=lambda *_args, **_kwargs: None,
            list_drafts=lambda: [],
        ),
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda path: widget if path == file_path_str else None,
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: False,
        apply_text_to_open_tab=lambda _path, _content: None,
        tab_index_for_path=lambda path: 0 if path == file_path_str else -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.editor_session_workflow"),
    )

    workflow.persist_session_state(project_root=str(project_root.resolve()))
    workflow.restore_session_state(str(project_root.resolve()))
    assert manager.open_paths() == [file_path_str]
