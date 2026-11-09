"""Deleting a file after a project switch still closes its editor tab."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.integration


def test_tree_delete_after_project_switch_closes_the_open_tab(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    project_one = tmp_path / "p1"
    project_two = tmp_path / "p2"
    create_blank_project(str(project_one.resolve()), project_name="One")
    create_blank_project(str(project_two.resolve()), project_name="Two")
    (project_one / "one.py").write_text("one = 1\n", encoding="utf-8")
    target = project_two / "two.py"
    target.write_text("two = 2\n", encoding="utf-8")
    target_path = str(target.resolve())

    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    assert window._file_project_commands_workflow.open_project_by_path(str(project_one.resolve())) is True
    assert window._file_project_commands_workflow.open_project_by_path(str(project_two.resolve())) is True
    assert window._editor_tab_factory.open_file_in_editor(target_path) is True
    assert window._editor_manager.get_tab(target_path) is not None

    assert window._project_tree_action_coordinator.handle_delete(target_path) is None
    app.processEvents()

    assert window._editor_manager.get_tab(target_path) is None
    assert target_path not in window._editor_manager.open_paths()
    assert window._editor_tabs_widget.count() == 0
    shutdown_main_window_for_test(window, app)
