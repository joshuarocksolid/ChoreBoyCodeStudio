"""Run/debug session orchestration helpers for shell layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from app.core import constants
from app.core.models import LoadedProject
from app.run.run_service import RunService, RunSession
from app.shell.actions import map_run_action_state
from app.shell.menus import MenuStubRegistry


class RunSessionStartFailureReason(str, Enum):
    """Stable reason codes for rejected run/debug start attempts."""

    NO_PROJECT = "no_project"
    ALREADY_RUNNING = "already_running"
    SAVE_FAILED = "save_failed"
    START_EXCEPTION = "start_exception"


@dataclass(frozen=True)
class RunSessionStartResult:
    """Result payload for run/debug/repl session start attempts."""

    started: bool
    failure_reason: RunSessionStartFailureReason | None = None
    error_message: str | None = None
    session: RunSession | None = None


class RunSessionController:
    """Coordinates run-service actions outside of main window class."""

    def __init__(self, run_service: RunService) -> None:
        self._run_service = run_service
        self._active_session_mode: str | None = None

    @property
    def active_session_mode(self) -> str | None:
        return self._active_session_mode

    def start_session(
        self,
        *,
        loaded_project: LoadedProject | None,
        mode: str,
        entry_file: str | None,
        argv: list[str] | None,
        working_directory: str | None,
        env_overrides: dict[str, str] | None,
        breakpoints: list[dict[str, int | str]] | None,
        skip_save: bool,
        save_all: Callable[[], bool],
        before_start: Callable[[], None],
        append_console_line: Callable[[str, str], None],
        append_python_console_line: Callable[[str], None],
    ) -> RunSessionStartResult:
        allows_projectless_entry = (
            loaded_project is None
            and entry_file is not None
            and mode in {constants.RUN_MODE_PYTHON_SCRIPT, constants.RUN_MODE_PYTHON_DEBUG}
        )
        if loaded_project is None and not allows_projectless_entry:
            return RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.NO_PROJECT,
                error_message="Open a project before running code.",
            )
        if self._run_service.supervisor.is_running():
            return RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
            )

        if loaded_project is not None and not skip_save and not save_all():
            return RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.SAVE_FAILED,
                error_message="Fix save errors before running.",
            )

        before_start()
        append_console_line("────────────────────\n", "system")
        append_console_line("Starting run...\n", "system")

        try:
            session = self._run_service.start_run(
                loaded_project,
                mode=mode,
                entry_file=entry_file,
                argv=argv,
                working_directory=working_directory,
                env_overrides=env_overrides,
                breakpoints=breakpoints,
            )
        except Exception as exc:
            append_console_line(f"Run failed to start: {exc}\n", "stderr")
            return RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.START_EXCEPTION,
                error_message=str(exc),
            )

        self._active_session_mode = mode
        append_console_line(f"Run started ({session.run_id})\n", "system")
        if mode == constants.RUN_MODE_PYTHON_DEBUG:
            append_python_console_line("[system] Debug session started. Use toolbar or pdb commands.")

        return RunSessionStartResult(started=True, session=session)

    def stop_session(self, append_console_line: Callable[[str, str], None]) -> None:
        self._run_service.stop_run()
        append_console_line("Stop requested.\n", "system")

    def clear_active_session_mode(self) -> None:
        self._active_session_mode = None

    def set_active_session_mode(self, mode: str | None) -> None:
        self._active_session_mode = mode

    def pause_session(
        self,
        *,
        append_python_console_line: Callable[[str], None],
        append_debug_output_line: Callable[[str], None],
    ) -> tuple[bool, str | None]:
        try:
            paused = self._run_service.pause_run()
        except Exception as exc:
            return (False, str(exc))
        if paused:
            append_python_console_line("[debug] Pause requested.")
            append_debug_output_line("[debug] Pause requested.")
        return (paused, None)

    def refresh_action_states(
        self,
        menu_registry: MenuStubRegistry | None,
        *,
        has_project: bool,
        has_active_file: bool = False,
        has_breakpoints: bool = False,
    ) -> None:
        if menu_registry is None:
            return

        run_action = menu_registry.action("shell.action.run.run")
        debug_action = menu_registry.action("shell.action.run.debug")
        run_project_action = menu_registry.action("shell.action.run.runProject")
        debug_project_action = menu_registry.action("shell.action.run.debugProject")
        stop_action = menu_registry.action("shell.action.run.stop")
        restart_action = menu_registry.action("shell.action.run.restart")
        continue_action = menu_registry.action("shell.action.run.continue")
        pause_action = menu_registry.action("shell.action.run.pause")
        step_over_action = menu_registry.action("shell.action.run.stepOver")
        step_into_action = menu_registry.action("shell.action.run.stepInto")
        step_out_action = menu_registry.action("shell.action.run.stepOut")
        toggle_breakpoint_action = menu_registry.action("shell.action.run.toggleBreakpoint")
        python_console_action = menu_registry.action("shell.action.run.pythonConsole")
        remove_all_bp_action = menu_registry.action("shell.action.run.removeAllBreakpoints")
        package_action = menu_registry.action("shell.action.build.package")

        state = map_run_action_state(
            has_project=has_project,
            has_active_file=has_active_file,
            is_running=self._run_service.supervisor.is_running(),
            is_debug_mode=self._run_service.is_debug_mode,
            is_debug_paused=self._run_service.is_debug_paused,
            has_breakpoints=has_breakpoints,
        )

        if run_action is not None:
            run_action.setEnabled(state.run_enabled)
        if debug_action is not None:
            debug_action.setEnabled(state.debug_enabled)
        if run_project_action is not None:
            run_project_action.setEnabled(state.run_project_enabled)
        if debug_project_action is not None:
            debug_project_action.setEnabled(state.debug_project_enabled)
        if stop_action is not None:
            stop_action.setEnabled(state.stop_enabled)
        if restart_action is not None:
            restart_action.setEnabled(state.restart_enabled)
        if continue_action is not None:
            continue_action.setEnabled(state.continue_enabled)
        if pause_action is not None:
            pause_action.setEnabled(state.pause_enabled)
        if step_over_action is not None:
            step_over_action.setEnabled(state.step_over_enabled)
        if step_into_action is not None:
            step_into_action.setEnabled(state.step_into_enabled)
        if step_out_action is not None:
            step_out_action.setEnabled(state.step_out_enabled)
        if toggle_breakpoint_action is not None:
            toggle_breakpoint_action.setEnabled(state.toggle_breakpoint_enabled)
        if python_console_action is not None:
            python_console_action.setEnabled(state.python_console_enabled)
        if remove_all_bp_action is not None:
            remove_all_bp_action.setEnabled(state.remove_all_breakpoints_enabled)
        if package_action is not None:
            package_action.setEnabled(state.package_enabled)

        project_gated_action_ids = (
            "shell.action.run.pytestProject",
            "shell.action.run.pytestCurrentFile",
            "shell.action.run.runWithConfig",
            "shell.action.run.manageRunConfigs",
        )
        for action_id in project_gated_action_ids:
            action = menu_registry.action(action_id)
            if action is not None:
                action.setEnabled(has_project and not state.stop_enabled)
