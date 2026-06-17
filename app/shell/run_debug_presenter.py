"""Run/debug UI presentation around the run-session controller."""

from __future__ import annotations

from typing import Any, Callable, Literal, Protocol

from PySide2.QtWidgets import QMessageBox, QWidget

from app.core import constants
from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.shell.run_session_controller import RunSessionController, RunSessionStartFailureReason


class RunDebugPresenterSaveWorkflowPort(Protocol):
    """Minimal save-workflow surface for pre-run save-all."""

    def handle_save_all_action(self) -> bool:
        ...


class RunDebugPresenterRunEventPort(Protocol):
    """Minimal run-event workflow surface for session start UI."""

    def append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        ...

    def bind_append_console_line(self) -> Callable[[str, str], None]:
        ...

    def set_run_status(self, status: str, *, return_code: int | None = None) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...


class RunDebugPresenterReplEventPort(Protocol):
    """Minimal REPL event workflow surface for debug-session notices."""

    def append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        ...


class RunDebugPresenterDebugPanelPort(Protocol):
    """Minimal debug panel surface toggled when debug sessions start."""

    def set_command_input_enabled(self, enabled: bool) -> None:
        ...


class RunDebugPresenterRunLaunchPort(Protocol):
    """Minimal run-launch workflow surface for restart relaunch."""

    def handle_run_action(self) -> None:
        ...

    def handle_rerun_last_debug_target_action(self) -> None:
        ...


class RunDebugPresenterRunServicePort(Protocol):
    """Minimal run-service surface for restart stop gating."""

    @property
    def supervisor(self) -> object:
        ...


class RunDebugPresenterEventBusPort(Protocol):
    """Minimal event bus surface for run-session lifecycle events."""

    def publish(self, event: object) -> None:
        ...


class RunDebugPresenterBottomTabsPort(Protocol):
    """Minimal bottom-tab widget surface for auto-opening run log."""

    def indexOf(self, widget: object) -> int:
        ...

    def setCurrentIndex(self, index: int) -> None:
        ...


class RunDebugPresenterHost(Protocol):
    """Host ports for :class:`RunDebugPresenter` (not ``window: Any``)."""

    def dialog_parent(self) -> QWidget:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def run_session_controller(self) -> RunSessionController:
        ...

    def save_workflow(self) -> RunDebugPresenterSaveWorkflowPort:
        ...

    def prepare_for_session_start(self) -> None:
        ...

    def run_event_workflow(self) -> RunDebugPresenterRunEventPort:
        ...

    def repl_event_workflow(self) -> RunDebugPresenterReplEventPort:
        ...

    def event_bus(self) -> RunDebugPresenterEventBusPort:
        ...

    def debug_panel(self) -> RunDebugPresenterDebugPanelPort | None:
        ...

    def auto_open_console_on_run_output(self) -> bool:
        ...

    def bottom_tabs_widget(self) -> RunDebugPresenterBottomTabsPort | None:
        ...

    def run_log_panel(self) -> object | None:
        ...

    def run_service(self) -> RunDebugPresenterRunServicePort:
        ...

    def run_launch_workflow(self) -> RunDebugPresenterRunLaunchPort:
        ...

    def is_shutting_down(self) -> bool:
        ...


PendingRestartKind = Literal["debug_target", "run"]


class RunDebugPresenterPort(Protocol):
    """Minimal presenter surface used to start run/debug sessions."""

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
        ...

    def stop_session(self) -> None:
        ...

    def restart_session(self) -> None:
        ...

    def execute_pending_restart_if_any(self) -> None:
        ...

    def clear_pending_restart(self) -> None:
        ...


__all__ = [
    "MainWindowRunDebugPresenterHost",
    "RunDebugPresenter",
    "RunDebugPresenterHost",
    "RunDebugPresenterPort",
]


class RunDebugPresenter:
    """Bridges run-session lifecycle outcomes into shell UI state."""

    def __init__(self, host: RunDebugPresenterHost) -> None:
        self._host = host
        self._pending_restart: PendingRestartKind | None = None

    def stop_session(self) -> None:
        host = self._host
        run_events = host.run_event_workflow()
        host.run_session_controller().stop_session(run_events.bind_append_console_line())
        run_events.set_run_status("stopping")
        run_events.refresh_run_action_states()

    def restart_session(self) -> None:
        host = self._host
        if host.run_service().supervisor.is_running():  # type: ignore[attr-defined]
            self._pending_restart = self._resolve_restart_kind()
            self.stop_session()
            return
        self._execute_restart()

    def execute_pending_restart_if_any(self) -> None:
        if self._pending_restart is None:
            return
        restart_kind = self._pending_restart
        self._pending_restart = None
        if self._host.is_shutting_down():
            return
        self._execute_restart(restart_kind)

    def clear_pending_restart(self) -> None:
        self._pending_restart = None

    def _resolve_restart_kind(self) -> PendingRestartKind:
        if self._host.run_session_controller().active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
            return "debug_target"
        return "run"

    def _execute_restart(self, restart_kind: PendingRestartKind | None = None) -> None:
        launch = self._host.run_launch_workflow()
        kind = restart_kind or self._resolve_restart_kind()
        if kind == "debug_target":
            launch.handle_rerun_last_debug_target_action()
        else:
            launch.handle_run_action()

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
        host = self._host
        run_events = host.run_event_workflow()
        result = host.run_session_controller().start_session(
            loaded_project=host.loaded_project(),
            mode=mode,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            skip_save=skip_save,
            save_all=host.save_workflow().handle_save_all_action,
            before_start=host.prepare_for_session_start,
            append_console_line=run_events.bind_append_console_line(),
            append_python_console_line=host.repl_event_workflow().append_python_console_line,
        )
        if not result.started:
            parent = host.dialog_parent()
            if result.failure_reason == RunSessionStartFailureReason.NO_PROJECT:
                QMessageBox.warning(parent, "Run unavailable", result.error_message or "No project is loaded.")
            elif result.failure_reason == RunSessionStartFailureReason.SAVE_FAILED:
                QMessageBox.warning(parent, "Run cancelled", result.error_message or "Save was cancelled.")
            elif result.failure_reason == RunSessionStartFailureReason.ALREADY_RUNNING:
                QMessageBox.warning(
                    parent,
                    "Run already in progress",
                    result.error_message or "A run is already in progress. Stop it before starting a new one.",
                )
            elif result.error_message:
                QMessageBox.warning(parent, "Run failed to start", result.error_message)
            run_events.set_run_status("idle")
            run_events.refresh_run_action_states()
            return False

        if result.session is not None:
            # Import lazily: events -> run -> plugins.contributions -> events.
            from app.shell.events import RunSessionStartedEvent

            host.event_bus().publish(
                RunSessionStartedEvent(
                    run_id=result.session.run_id,
                    mode=result.session.mode,
                    entry_file=result.session.entry_file,
                    project_root=result.session.project_root,
                )
            )
        debug_panel = host.debug_panel()
        if debug_panel is not None:
            debug_panel.set_command_input_enabled(
                host.run_session_controller().active_session_mode == constants.RUN_MODE_PYTHON_DEBUG
            )
        run_events.set_run_status("running")
        if host.auto_open_console_on_run_output():
            bottom_tabs = host.bottom_tabs_widget()
            run_log = host.run_log_panel()
            if bottom_tabs is not None and run_log is not None:
                index = bottom_tabs.indexOf(run_log)
                if index >= 0:
                    bottom_tabs.setCurrentIndex(index)
        run_events.refresh_run_action_states()
        return True


class MainWindowRunDebugPresenterHost:
    """Adapts :class:`MainWindow` to :class:`RunDebugPresenterHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> QWidget:
        return self._window

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def run_session_controller(self) -> RunSessionController:
        return self._window._run_session_controller

    def save_workflow(self) -> RunDebugPresenterSaveWorkflowPort:
        return self._window._save_workflow

    def prepare_for_session_start(self) -> None:
        self._window._python_console_workflow.prepare_for_session_start()

    def run_event_workflow(self) -> RunDebugPresenterRunEventPort:
        return self._window._run_event_workflow

    def repl_event_workflow(self) -> RunDebugPresenterReplEventPort:
        return self._window._repl_event_workflow

    def event_bus(self) -> RunDebugPresenterEventBusPort:
        return self._window._event_bus

    def debug_panel(self) -> RunDebugPresenterDebugPanelPort | None:
        return self._window._debug_panel

    def auto_open_console_on_run_output(self) -> bool:
        return self._window._auto_open_console_on_run_output

    def bottom_tabs_widget(self) -> RunDebugPresenterBottomTabsPort | None:
        return self._window._bottom_tabs_widget

    def run_log_panel(self) -> object | None:
        return self._window._run_log_panel

    def run_service(self) -> RunDebugPresenterRunServicePort:
        return self._window._run_service

    def run_launch_workflow(self) -> RunDebugPresenterRunLaunchPort:
        return self._window._run_launch_workflow

    def is_shutting_down(self) -> bool:
        return bool(getattr(self._window, "_is_shutting_down", False))
