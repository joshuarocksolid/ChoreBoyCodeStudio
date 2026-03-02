"""Run/debug session orchestration helpers for shell layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core import constants
from app.core.models import LoadedProject
from app.run.run_service import RunService, RunSession
from app.shell.actions import map_run_action_state
from app.shell.menus import MenuStubRegistry


@dataclass(frozen=True)
class RunSessionStartResult:
    """Result payload for run/debug/repl session start attempts."""

    started: bool
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
        safe_mode: bool | None,
        breakpoints: list[dict[str, int | str]] | None,
        skip_save: bool,
        save_all: Callable[[], bool],
        before_start: Callable[[], None],
        append_console_line: Callable[[str, str], None],
        append_python_console_line: Callable[[str], None],
    ) -> RunSessionStartResult:
        if loaded_project is None and mode != constants.RUN_MODE_PYTHON_REPL:
            return RunSessionStartResult(started=False, error_message="Open a project before running code.")
        if self._run_service.supervisor.is_running():
            return RunSessionStartResult(started=False)

        if not skip_save and not save_all():
            return RunSessionStartResult(started=False, error_message="Fix save errors before running.")

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
                safe_mode=safe_mode,
                breakpoints=breakpoints,
            )
        except Exception as exc:
            append_console_line(f"Run failed to start: {exc}\n", "stderr")
            return RunSessionStartResult(started=False, error_message=str(exc))

        self._active_session_mode = mode
        append_console_line(f"Run started ({session.run_id})\n", "system")
        if mode == constants.RUN_MODE_PYTHON_REPL:
            append_python_console_line("[system] Python console started.")
        elif mode == constants.RUN_MODE_PYTHON_DEBUG:
            append_python_console_line("[system] Debug session started. Use toolbar or pdb commands.")

        return RunSessionStartResult(started=True, session=session)

    def stop_session(self, append_console_line: Callable[[str, str], None]) -> None:
        self._run_service.stop_run()
        append_console_line("Stop requested.\n", "system")

    def clear_active_session_mode(self) -> None:
        self._active_session_mode = None

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

    def refresh_action_states(self, menu_registry: MenuStubRegistry | None, *, has_project: bool) -> None:
        if menu_registry is None:
            return

        run_action = menu_registry.action("shell.action.run.run")
        debug_action = menu_registry.action("shell.action.run.debug")
        stop_action = menu_registry.action("shell.action.run.stop")
        restart_action = menu_registry.action("shell.action.run.restart")
        continue_action = menu_registry.action("shell.action.run.continue")
        pause_action = menu_registry.action("shell.action.run.pause")
        step_over_action = menu_registry.action("shell.action.run.stepOver")
        step_into_action = menu_registry.action("shell.action.run.stepInto")
        step_out_action = menu_registry.action("shell.action.run.stepOut")
        toggle_breakpoint_action = menu_registry.action("shell.action.run.toggleBreakpoint")
        python_console_action = menu_registry.action("shell.action.run.pythonConsole")

        state = map_run_action_state(
            has_project=has_project,
            is_running=self._run_service.supervisor.is_running(),
            is_debug_mode=self._run_service.is_debug_mode,
            is_debug_paused=self._run_service.is_debug_paused,
        )

        if run_action is not None:
            run_action.setEnabled(state.run_enabled)
        if debug_action is not None:
            debug_action.setEnabled(state.debug_enabled)
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
