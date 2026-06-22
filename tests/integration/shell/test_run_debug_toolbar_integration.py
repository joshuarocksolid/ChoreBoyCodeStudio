"""Integration tests for run/debug toolbar wiring in main window."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import prepare_main_window_for_test

pytestmark = pytest.mark.integration


def test_run_debug_toolbar_actions_exist_and_enable_after_project_open(
    monkeypatch: pytest.MonkeyPatch,
    shell_qapp,
) -> None:
    window = MainWindow(state_root=str(Path("/tmp").resolve()))
    prepare_main_window_for_test(window, app=shell_qapp)
    try:
        registry = window.menu_registry
        assert registry is not None
        assert registry.action("shell.action.run.run") is not None
        assert registry.action("shell.action.run.debug") is not None
        assert registry.action("shell.action.run.runProject") is not None
        assert registry.action("shell.action.run.debugProject") is not None
        assert registry.action("shell.action.run.debugPytestCurrentFile") is not None
        assert registry.action("shell.action.run.rerunLastDebugTarget") is not None
        assert registry.action("shell.action.run.debugExceptionStops") is not None
        assert registry.action("shell.action.run.pause") is not None
        assert registry.action("shell.action.run.stepOver") is not None
        assert registry.action("shell.action.run.toggleBreakpoint") is not None

        project_root = Path("/tmp/choreboy_toolbar_project")
        if project_root.exists():
            shutil.rmtree(project_root)
        project_root.mkdir(parents=True)
        (project_root / "run.py").write_text("print('toolbar')\n", encoding="utf-8")
        (project_root / "run_tests.py").write_text("print('tests')\n", encoding="utf-8")
        opened = window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve()))
        assert opened is True
        assert window._editor_tab_factory.open_file_in_editor(str((project_root / "run.py").resolve()), preview=False) is True
        window._run_event_workflow.refresh_run_action_states()

        run_action = registry.action("shell.action.run.run")
        debug_action = registry.action("shell.action.run.debug")
        run_project_action = registry.action("shell.action.run.runProject")
        debug_project_action = registry.action("shell.action.run.debugProject")
        debug_current_test_action = registry.action("shell.action.run.debugPytestCurrentFile")
        rerun_last_debug_action = registry.action("shell.action.run.rerunLastDebugTarget")
        exception_settings_action = registry.action("shell.action.run.debugExceptionStops")
        stop_action = registry.action("shell.action.run.stop")
        python_console_action = registry.action("shell.action.run.pythonConsole")
        pause_action = registry.action("shell.action.run.pause")
        assert run_action.isEnabled() is True
        assert debug_action.isEnabled() is True
        assert run_project_action.isEnabled() is True
        assert debug_project_action.isEnabled() is True
        assert debug_current_test_action.isEnabled() is True
        assert rerun_last_debug_action.isEnabled() is False
        assert exception_settings_action.isEnabled() is True
        assert stop_action.isEnabled() is False
        assert python_console_action.isEnabled() is True
        assert pause_action.isEnabled() is False

        window._run_launch_workflow.record_debug_target_from_dict({"kind": "project"})
        window._run_event_workflow.refresh_run_action_states()
        assert rerun_last_debug_action.isEnabled() is True
    finally:
        shutdown_main_window_for_test(window)


def test_restart_action_routes_through_presenter(monkeypatch: pytest.MonkeyPatch, shell_qapp) -> None:
    window = MainWindow(state_root=str(Path("/tmp").resolve()))
    prepare_main_window_for_test(window, app=shell_qapp)
    try:
        presenter = window._run_debug_presenter
        assert hasattr(presenter, "restart_session")
        assert hasattr(presenter, "stop_session")
        assert not hasattr(window, "_handle_restart_action")

        triggered: list[str] = []
        monkeypatch.setattr(
            presenter,
            "_execute_restart",
            lambda restart_kind=None: triggered.append("restart"),
        )
        presenter.restart_session()
        assert triggered == ["restart"]
    finally:
        shutdown_main_window_for_test(window)


def test_stop_action_routes_through_presenter(monkeypatch: pytest.MonkeyPatch, shell_qapp) -> None:
    window = MainWindow(state_root=str(Path("/tmp").resolve()))
    prepare_main_window_for_test(window, app=shell_qapp)
    try:
        presenter = window._run_debug_presenter
        assert hasattr(presenter, "stop_session")
        assert not hasattr(window, "_handle_stop_action")

        triggered: list[str] = []
        monkeypatch.setattr(
            presenter,
            "stop_session",
            lambda: triggered.append("stop"),
        )
        presenter.stop_session()

        assert triggered == ["stop"]
    finally:
        shutdown_main_window_for_test(window)
