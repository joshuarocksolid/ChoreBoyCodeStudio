"""Realtime lint must survive EditorManager replacement on project open."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import (
    apply_standard_main_window_test_patches,
    wait_for,
)

pytestmark = pytest.mark.integration


def _prepare_window_keeping_realtime_lint(window: MainWindow, app) -> None:  # type: ignore[no-untyped-def]
    """Stop noisy timers but keep the realtime lint timer alive."""
    for name in (
        "_auto_save_to_file_timer",
        "_project_tree_preview_click_timer",
        "_run_event_timer",
        "_repl_event_timer",
        "_external_change_poll_timer",
        "_restore_project_timer",
        "_auto_start_repl_timer",
        "_runtime_probe_timer",
        "_startup_probe_refresh_timer",
        "_outline_refresh_timer",
    ):
        timer = getattr(window, name, None)
        if timer is not None:
            timer.stop()
    apply_standard_main_window_test_patches(window)
    app.processEvents()


def test_realtime_lint_clears_overlays_after_project_open_replaces_editor_manager(
    tmp_path: Path,
    shell_qapp,
) -> None:
    """Regression: stale bound active_file_path made realtime lint a no-op after open."""
    app = shell_qapp
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Realtime Lint Project")
    target = project_root / "main.py"
    bad = "def broken(\n    print('oops')\n"
    good = "def broken():\n    print('oops')\n"
    target.write_text(bad, encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    manager_at_compose = window._editor_manager
    _prepare_window_keeping_realtime_lint(window, app)

    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    assert window._editor_manager is not manager_at_compose

    path = str(target.resolve())
    assert window._editor_tab_factory.open_file_in_editor(path, preview=False) is True
    app.processEvents()

    # Live lookup must follow the replaced manager (the bug returned None forever).
    assert window._diagnostics_orchestrator._get_active_tab_file_path() == path

    realtime_triggers: list[str] = []
    original_render = window._lint_workflow.render_diagnostics_for_file

    def _spy_render(file_path: str, *, trigger: str) -> None:
        if trigger == "realtime":
            realtime_triggers.append(file_path)
        original_render(file_path, trigger=trigger)

    window._lint_workflow.render_diagnostics_for_file = _spy_render  # type: ignore[method-assign]

    editor = window._editor_widgets_by_path[path]
    window._lint_workflow.render_diagnostics_for_file(path, trigger="manual")
    assert wait_for(
        lambda: len(editor._diagnostic_selections) > 0
        and len(window._stored_lint_diagnostics.get(path, [])) > 0,
        app,
        timeout_seconds=8.0,
    )

    editor.setPlainText(good)
    assert wait_for(
        lambda: path in realtime_triggers
        and len(editor._diagnostic_selections) == 0
        and len(window._stored_lint_diagnostics.get(path, [])) == 0,
        app,
        timeout_seconds=8.0,
    )

    shutdown_main_window_for_test(window, app)


def test_orchestrator_active_path_follows_replaced_editor_manager(
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Active Path Project")
    target = project_root / "main.py"
    target.write_text("print(1)\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    stale_bound = window._editor_manager.active_file_path
    _prepare_window_keeping_realtime_lint(window, app)

    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    path = str(target.resolve())
    assert window._editor_tab_factory.open_file_in_editor(path, preview=False) is True
    app.processEvents()

    assert stale_bound() is None
    assert window._diagnostics_orchestrator._get_active_tab_file_path() == path
    assert window._editor_manager.active_file_path() == path

    shutdown_main_window_for_test(window, app)
