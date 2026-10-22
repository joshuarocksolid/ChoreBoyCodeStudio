"""Stale and missing tab markers, tooltips, and info bars in the real shell."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING  # noqa: E402
from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.editor_tab_bar import TAB_TOOLTIP_MISSING, TAB_TOOLTIP_STALE  # noqa: E402
from app.shell.editor_tab_page import EditorTabPage  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.integration


def test_stale_and_missing_markers_follow_the_buffer_conflict(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Tab States")
    report = project_root / "report.py"
    report.write_text("print('v1')\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    report_path = str(report.resolve())
    assert window._editor_tab_factory.open_file_in_editor(report_path) is True
    tabs = window._editor_tabs_widget
    index = window._editor_tab_workflow.tab_index_for_path(report_path)
    page = tabs.widget(index)
    assert isinstance(page, EditorTabPage)
    plain_width = tabs.tabBar().tabSizeHint(index).width()
    assert page.info_bar.isHidden()

    tab = window._editor_manager.get_tab(report_path)
    tab.set_disk_conflict(DISK_CONFLICT_CHANGED, 2.0)
    window._editor_tab_workflow.refresh_tab_presentation(report_path)

    assert tabs.tabBar().tabData(index)["is_stale"] is True
    assert TAB_TOOLTIP_STALE in tabs.tabToolTip(index)
    assert tabs.tabBar().tabSizeHint(index).width() > plain_width
    assert not page.info_bar.isHidden()
    assert page.info_bar.message() == "report.py changed on disk after you opened it. You kept your version."

    tab.set_disk_conflict(DISK_CONFLICT_MISSING, None)
    window._editor_tab_workflow.refresh_tab_presentation(report_path)

    assert tabs.tabBar().tabData(index)["is_missing"] is True
    assert TAB_TOOLTIP_MISSING in tabs.tabToolTip(index)
    assert page.info_bar.message() == "report.py is not on disk any more. Your text is still here."

    tab.clear_disk_conflict()
    window._editor_tab_workflow.refresh_tab_presentation(report_path)
    assert page.info_bar.isHidden()
    assert tabs.tabBar().tabSizeHint(index).width() == plain_width
    shutdown_main_window_for_test(window, app)
