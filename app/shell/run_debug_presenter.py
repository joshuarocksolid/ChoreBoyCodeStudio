"""Run/debug UI presentation around the run-session controller."""

from __future__ import annotations

from typing import Any

from PySide2.QtWidgets import QMessageBox

from app.core import constants
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.shell.events import RunSessionStartedEvent
from app.shell.run_log_panel import RunInfo
from app.shell.run_session_controller import RunSessionStartFailureReason


class RunDebugPresenter:
    """Bridges run-session lifecycle outcomes into shell UI state."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def start_session(
        self,
        *,
        mode: str,
        entry_file: str | None = None,
        argv: list[str] | None = None,
        working_directory: str | None = None,
        env_overrides: dict[str, str] | None = None,
        breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
        debug_exception_policy: DebugExceptionPolicy | None = None,
        source_maps: list[DebugSourceMap] | None = None,
        skip_save: bool = False,
    ) -> bool:
        window = self._window
        result = window._run_session_controller.start_session(
            loaded_project=window._loaded_project,
            mode=mode,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            skip_save=skip_save,
            save_all=window._save_workflow.handle_save_all_action,
            before_start=window._prepare_for_session_start,
            append_console_line=lambda text, stream: window._append_console_line(text, stream=stream),
            append_python_console_line=window._append_python_console_line,
        )
        if not result.started:
            if result.failure_reason == RunSessionStartFailureReason.NO_PROJECT:
                QMessageBox.warning(window, "Run unavailable", result.error_message or "No project is loaded.")
            elif result.failure_reason == RunSessionStartFailureReason.SAVE_FAILED:
                QMessageBox.warning(window, "Run cancelled", result.error_message or "Save was cancelled.")
            elif result.failure_reason == RunSessionStartFailureReason.ALREADY_RUNNING:
                pass
            elif result.error_message:
                QMessageBox.warning(window, "Run failed to start", result.error_message)
            window._set_run_status("idle")
            window._refresh_run_action_states()
            return False

        if result.session is not None:
            window._active_run_session_log_path = result.session.log_file_path
            window._active_run_session_info = RunInfo(
                run_id=result.session.run_id,
                mode=result.session.mode,
                entry_file=result.session.entry_file,
            )
            window._event_bus.publish(
                RunSessionStartedEvent(
                    run_id=result.session.run_id,
                    mode=result.session.mode,
                    entry_file=result.session.entry_file,
                    project_root=result.session.project_root,
                )
            )
        if window._debug_panel is not None:
            window._debug_panel.set_command_input_enabled(
                window._run_session_controller.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG
            )
        window._set_run_status("running")
        if window._auto_open_console_on_run_output:
            window._focus_run_log_tab()
        window._refresh_run_action_states()
        return True
