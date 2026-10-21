"""Open editor buffers keep working after their file is renamed or moved."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QEvent, QPoint  # noqa: E402
from app.qt.QtGui import QHelpEvent  # noqa: E402

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test, wait_for  # noqa: E402

pytestmark = pytest.mark.integration


def _open_project_file(tmp_path: Path, app: Any) -> tuple[MainWindow, Path, str]:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Buffer Identity")
    (project_root / "pkg").mkdir()
    source = project_root / "solo_module.py"
    source.write_text("value = 1\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    prepare_main_window_for_test(window, app=app)
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    source_path = str(source.resolve())
    assert window._editor_tab_factory.open_file_in_editor(source_path) is True
    return window, project_root.resolve(), source_path


def _rename(window: MainWindow, source_path: str, project_root: Path) -> str:
    assert window._project_tree_action_coordinator.handle_rename(source_path, "renamed_module.py") is None
    return str(project_root / "renamed_module.py")


def _cut_paste(window: MainWindow, source_path: str, project_root: Path) -> str:
    failed, _paths, _cut = window._project_tree_action_coordinator.handle_paste(
        destination_directory=str(project_root / "pkg"),
        clipboard_paths=[source_path],
        clipboard_cut=True,
    )
    assert failed == []
    return str(project_root / "pkg" / "solo_module.py")


@pytest.mark.parametrize("move", [_rename, _cut_paste], ids=["rename", "cut_paste"])
def test_edit_after_move_marks_buffer_dirty_and_saves_to_new_path(
    tmp_path: Path,
    shell_qapp,
    move,
) -> None:
    window, project_root, source_path = _open_project_file(tmp_path, shell_qapp)
    try:
        moved_path = move(window, source_path, project_root)
        editor = window._workspace_controller.widget_for_path(moved_path)
        assert editor is not None

        editor.setPlainText("value = 2\n")

        tab = window._editor_manager.get_tab(moved_path)
        assert tab is not None
        assert tab.is_dirty is True
        assert tab.current_content == "value = 2\n"
        assert window._save_workflow.handle_save_action() is True
        assert Path(moved_path).read_text(encoding="utf-8") == "value = 2\n"
        assert not Path(source_path).exists()
    finally:
        shutdown_main_window_for_test(window, shell_qapp)


def test_completion_and_hover_after_rename_request_the_new_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    window, project_root, source_path = _open_project_file(tmp_path, shell_qapp)
    try:
        moved_path = _rename(window, source_path, project_root)
        semantic_navigation = window._semantic_navigation_workflow
        completion_paths: list[str] = []
        hover_paths: list[str] = []
        monkeypatch.setattr(
            semantic_navigation,
            "request_editor_completions_async",
            lambda **kwargs: completion_paths.append(kwargs["file_path"]),
        )
        monkeypatch.setattr(
            semantic_navigation,
            "request_inline_hover_text_async",
            lambda **kwargs: hover_paths.append(kwargs["file_path"]),
        )
        window._editor_hover_tooltip_enabled = True
        window._editor_tab_workflow.apply_editor_preferences_to_open_editors()
        editor = window._workspace_controller.widget_for_path(moved_path)
        assert editor is not None

        editor.trigger_completion(manual=True)
        editor.event(QHelpEvent(QEvent.ToolTip, QPoint(2, 2), QPoint(2, 2)))

        assert completion_paths == [moved_path]
        assert hover_paths == [moved_path]
    finally:
        shutdown_main_window_for_test(window, shell_qapp)


def test_session_restore_after_move_reopens_new_path_with_buffer_text(
    tmp_path: Path,
    shell_qapp,
) -> None:
    window, project_root, source_path = _open_project_file(tmp_path, shell_qapp)
    try:
        moved_path = _cut_paste(window, source_path, project_root)

        window._local_history_workflow.persist_session_state()
        window._editor_tab_workflow.reset_editor_tabs()
        window._local_history_workflow.restore_session_state(str(project_root))

        assert wait_for(lambda: window._editor_manager.open_paths() == [moved_path], shell_qapp, timeout_seconds=0.5)
        editor = window._workspace_controller.widget_for_path(moved_path)
        assert editor is not None
        assert editor.toPlainText() == "value = 1\n"
    finally:
        shutdown_main_window_for_test(window, shell_qapp)
