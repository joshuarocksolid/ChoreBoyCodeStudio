"""Status bar: the completion mode chip and the active tab's disk state, in the real shell."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING  # noqa: E402
from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.integration


def _window_with_project(tmp_path: Path, app, *, project_mode: str | None = None):  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Status")
    report = project_root / "report.py"
    report.write_text("print('v1')\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    if project_mode is not None:
        window._settings_service.save_project(
            str(project_root.resolve()), {"intelligence": {"completion_mode": project_mode}}
        )
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    return window, str(report.resolve())


def test_completion_chip_names_the_global_mode_by_default(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    window, _report = _window_with_project(tmp_path, shell_qapp)

    assert window._status_controller.completion_mode_text() == "Completion: Manual · Ctrl+Space (Global setting)"
    shutdown_main_window_for_test(window, shell_qapp)


def test_completion_chip_names_a_project_override(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    window, _report = _window_with_project(tmp_path, shell_qapp, project_mode="typing")

    assert window._status_controller.completion_mode_text() == "Completion: While typing (Project setting)"
    shutdown_main_window_for_test(window, shell_qapp)


@pytest.mark.parametrize(
    ("kind", "suffix"),
    [(DISK_CONFLICT_CHANGED, "| saved | changed on disk"), (DISK_CONFLICT_MISSING, "| missing from disk")],
)
def test_editor_status_shows_the_active_tabs_disk_state(tmp_path: Path, shell_qapp, kind: str, suffix: str) -> None:  # type: ignore[no-untyped-def]
    window, report = _window_with_project(tmp_path, shell_qapp)
    assert window._editor_tab_factory.open_file_in_editor(report) is True
    tab = window._editor_manager.get_tab(report)

    tab.set_disk_conflict(kind, 2.0 if kind == DISK_CONFLICT_CHANGED else None)
    window._editor_tab_workflow.refresh_tab_presentation(report)
    assert window._status_controller.editor_status_text().endswith(suffix)

    tab.clear_disk_conflict()
    window._editor_tab_workflow.refresh_tab_presentation(report)
    assert window._status_controller.editor_status_text().endswith("| saved")
    shutdown_main_window_for_test(window, shell_qapp)
