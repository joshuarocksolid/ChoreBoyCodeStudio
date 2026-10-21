"""Split editor groups in the real shell: shared buffers, focus, close prompts, session."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide2.QtGui import QMouseEvent, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication, QFrame, QSplitter  # noqa: E402

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.document_safety import DocumentCloseIntent, DocumentSafetyDecision  # noqa: E402
from app.shell.editor_tab_page import page_editor  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test, wait_for  # noqa: E402

pytestmark = pytest.mark.integration


def _open_window(tmp_path: Path, app, names: tuple[str, ...]):  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Groups")
    paths = []
    for name in names:
        file_path = project_root / name
        file_path.write_text(f"# {name}\n", encoding="utf-8")
        paths.append(str(file_path.resolve()))
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    window.resize(1400, 800)
    window.show()
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    for file_path in paths:
        assert window._editor_tab_factory.open_file_in_editor(file_path) is True
    app.processEvents()
    return window, project_root, paths


def _labels(tabs) -> list[str]:  # type: ignore[no-untyped-def]
    return [tabs.tabText(index) for index in range(tabs.count())]


def _type_at_end(editor, text: str) -> None:  # type: ignore[no-untyped-def]
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    cursor.insertText(text)


def test_one_buffer_in_two_groups_has_one_dirty_state(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, _root, (alpha,) = _open_window(tmp_path, app, ("alpha.py",))
    groups = window._editor_groups

    assert groups.split_right() is True
    first, second = groups.tab_widgets()
    assert groups.focused_index() == 1 and window._editor_tabs_widget is second
    first_view = page_editor(first.widget(0))
    second_view = page_editor(second.widget(0))
    assert first_view is not second_view and second_view.document() is first_view.document()

    _type_at_end(second_view, "x = 1\n")
    app.processEvents()

    assert _labels(first) == ["alpha.py *"] and _labels(second) == ["alpha.py *"]
    assert window._editor_manager.get_tab(alpha).is_dirty

    groups.focus_group(0)
    assert window._save_workflow.handle_save_action() is True
    app.processEvents()

    assert Path(alpha).read_text(encoding="utf-8").endswith("x = 1\n")
    assert _labels(first) == ["alpha.py"] and _labels(second) == ["alpha.py"]
    shutdown_main_window_for_test(window, app)


def test_actions_target_the_focused_group(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, _root, (alpha, beta) = _open_window(tmp_path, app, ("alpha.py", "beta.py"))
    groups = window._editor_groups
    first = groups.tab_widgets()[0]
    first.setCurrentIndex(window._editor_tab_workflow.tab_index_for_path(beta))
    groups.split_right()
    assert window._editor_manager.active_file_path() == beta

    groups.focus_group(0)
    first.setCurrentIndex(window._editor_tab_workflow.tab_index_for_path(alpha))
    assert window._editor_manager.active_file_path() == alpha
    assert window._editor_tab_workflow.active_editor_widget() is page_editor(first.currentWidget())

    groups.focus_group(1)
    second = groups.tab_widgets()[1]
    assert window._editor_manager.active_file_path() == beta
    assert window._editor_tab_workflow.active_editor_widget() is page_editor(second.currentWidget())
    _type_at_end(page_editor(second.currentWidget()), "y = 2\n")
    assert window._save_workflow.handle_save_action() is True
    assert Path(beta).read_text(encoding="utf-8").endswith("y = 2\n")
    assert not Path(alpha).read_text(encoding="utf-8").endswith("y = 2\n")
    shutdown_main_window_for_test(window, app)


def test_closing_a_group_asks_about_buffers_open_only_there(tmp_path: Path, shell_qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, _root, (alpha, beta) = _open_window(tmp_path, app, ("alpha.py", "beta.py"))
    groups = window._editor_groups
    first = groups.tab_widgets()[0]
    first.setCurrentIndex(window._editor_tab_workflow.tab_index_for_path(beta))
    groups.split_right()
    groups.move_buffer(groups.groups()[0], window._editor_manager.get_tab(beta).buffer_id, groups.groups()[1])
    _type_at_end(page_editor(groups.tab_widgets()[1].currentWidget()), "z = 3\n")
    asked: list[tuple[str, ...]] = []
    answers = [DocumentCloseIntent.CANCEL, DocumentCloseIntent.DISCARD]

    def decide(action_description, *, scope, allow_keep_for_next_launch, dirty_buffers=None):  # type: ignore[no-untyped-def]
        asked.append(tuple(tab.file_path for tab in dirty_buffers or ()))
        return DocumentSafetyDecision(intent=answers.pop(0), scope=scope)

    monkeypatch.setattr(window._save_workflow, "request_unsaved_changes_decision", decide)

    assert groups.close_group(1) is False
    assert groups.group_count() == 2 and asked == [(beta,)]

    assert groups.close_group(1) is True
    app.processEvents()
    assert groups.group_count() == 1
    assert window._editor_manager.open_paths() == [alpha]
    assert window._editor_tabs_widget is groups.tab_widgets()[0]
    shutdown_main_window_for_test(window, app)


def test_dragging_a_tab_down_into_the_other_group_moves_it(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, _root, (alpha, beta) = _open_window(tmp_path, app, ("alpha.py", "beta.py"))
    groups = window._editor_groups
    groups.split_right()  # beta now shows in both groups
    groups.focus_group(0)
    first, second = groups.tab_widgets()
    bar = first.tabBar()
    alpha_index = window._editor_tab_workflow.tab_index_for_path(alpha)
    start = bar.tabRect(alpha_index).center()
    drop = bar.mapFromGlobal(second.mapToGlobal(second.rect().center()))

    def mouse(kind, pos: QPoint, buttons) -> None:  # type: ignore[no-untyped-def]
        QApplication.sendEvent(bar, QMouseEvent(kind, pos, bar.mapToGlobal(pos), Qt.LeftButton, buttons, Qt.NoModifier))

    mouse(QEvent.MouseButtonPress, start, Qt.LeftButton)
    for step in range(1, 6):
        mouse(QEvent.MouseMove, start + (drop - start) * step / 5, Qt.LeftButton)
    overlay = window.findChild(QFrame, "shell.editorGroups.dropOverlay")
    assert overlay is not None and overlay.isVisible()
    assert overlay.geometry().width() == groups.groups()[1].width()
    assert window.findChild(QSplitter, "shell.editorGroups").count() == 2
    mouse(QEvent.MouseButtonRelease, drop, Qt.NoButton)
    assert not overlay.isVisible()
    app.processEvents()

    assert [label.rstrip(" *") for label in _labels(first)] == ["beta.py"]
    assert [label.rstrip(" *") for label in _labels(second)] == ["beta.py", "alpha.py"]
    assert groups.focused_index() == 1
    assert window._editor_manager.active_file_path() == alpha
    shutdown_main_window_for_test(window, app)


def test_group_layout_survives_session_restore(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, root, (alpha, beta, gamma) = _open_window(tmp_path, app, ("alpha.py", "beta.py", "gamma.py"))
    groups = window._editor_groups
    first = groups.tab_widgets()[0]
    first.setCurrentIndex(window._editor_tab_workflow.tab_index_for_path(beta))
    groups.split_right()
    groups.move_buffer(groups.groups()[0], window._editor_manager.get_tab(gamma).buffer_id, groups.groups()[1])

    window._local_history_workflow.persist_session_state()
    window._editor_tab_workflow.reset_editor_tabs()
    assert groups.group_count() == 1
    window._local_history_workflow.restore_session_state(str(root.resolve()))
    assert wait_for(lambda: groups.group_count() == 2, app, timeout_seconds=2.0)

    first, second = groups.tab_widgets()
    assert _labels(first) == ["alpha.py", "beta.py"]
    assert _labels(second) == ["beta.py", "gamma.py"]
    assert second.currentIndex() == 1 and groups.focused_index() == 1
    assert window._editor_manager.open_paths() == [alpha, beta, gamma]
    shutdown_main_window_for_test(window, app)
