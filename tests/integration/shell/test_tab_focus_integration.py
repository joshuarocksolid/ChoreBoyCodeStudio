"""Tab moves focus across the shell and still indents in code editors."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QToolButton  # noqa: E402

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.editor_tab_page import page_editor  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test, wait_for  # noqa: E402

pytestmark = pytest.mark.integration


def _open_window(tmp_path: Path, app):  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="TabFocus")
    file_path = project_root / "alpha.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    window.resize(1200, 800)
    window.show()
    window.activateWindow()
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    app.processEvents()
    return window, str(file_path.resolve())


def _press(app, key) -> None:  # type: ignore[no-untyped-def]
    QTest.keyClick(QApplication.focusWidget(), key)
    app.processEvents()


def test_tab_moves_focus_from_activity_bar_into_project_tree(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, _alpha = _open_window(tmp_path, app)
    explorer = window.findChild(QToolButton, "shell.activityBar.btn.explorer")
    tree = window._project_tree_widget
    explorer.setFocus(Qt.TabFocusReason)
    assert wait_for(lambda: QApplication.focusWidget() is explorer, app)

    _press(app, Qt.Key_Tab)
    assert QApplication.focusWidget() is not explorer
    for _ in range(10):
        if QApplication.focusWidget() is tree:
            break
        _press(app, Qt.Key_Tab)
    assert QApplication.focusWidget() is tree

    _press(app, Qt.Key_Backtab)
    assert QApplication.focusWidget() is not tree
    shutdown_main_window_for_test(window, app)


def test_tab_still_indents_in_code_editor(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    window, alpha = _open_window(tmp_path, app)
    assert window._editor_tab_factory.open_file_in_editor(alpha) is True
    tabs = window._editor_tabs_widget
    assert tabs is not None
    editor = page_editor(tabs.currentWidget())
    editor.setFocus(Qt.OtherFocusReason)
    assert wait_for(lambda: QApplication.focusWidget() is editor, app)

    _press(app, Qt.Key_Tab)

    assert QApplication.focusWidget() is editor
    assert editor.toPlainText().startswith(("    x = 1", "\tx = 1"))
    shutdown_main_window_for_test(window, app)
