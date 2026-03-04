"""Coordinator for run/debug output and lifecycle event routing."""

from __future__ import annotations

from typing import Callable

from app.core import constants
from app.debug.debug_session import DebugSession
from app.run.problem_parser import ProblemEntry
from app.run.process_supervisor import ProcessEvent


class RunOutputCoordinator:
    """Routes run-process events to shell-side output/debug handlers."""

    def __init__(
        self,
        *,
        is_shutting_down: Callable[[], bool],
        get_active_session_mode: Callable[[], str | None],
        set_active_session_mode: Callable[[str | None], None],
        get_debug_session: Callable[[], DebugSession],
        append_output_tail: Callable[[str], None],
        append_console_line: Callable[[str, str], None],
        append_debug_output_line: Callable[[str], None],
        apply_debug_inspector_event: Callable[[], None],
        refresh_run_action_states: Callable[[], None],
        set_run_status: Callable[[str, int | None], None],
        focus_run_log_tab: Callable[[], None],
        focus_problems_tab: Callable[[], None],
        set_debug_command_input_enabled: Callable[[bool], None],
        clear_controller_active_session_mode: Callable[[], None],
        finalize_run_log: Callable[[int | None], None],
        update_problems_from_output: Callable[[], list[ProblemEntry]],
        auto_open_console_on_run_output_enabled: Callable[[], bool],
        auto_open_problems_on_run_failure_enabled: Callable[[], bool],
    ) -> None:
        self._is_shutting_down = is_shutting_down
        self._get_active_session_mode = get_active_session_mode
        self._set_active_session_mode = set_active_session_mode
        self._get_debug_session = get_debug_session
        self._append_output_tail = append_output_tail
        self._append_console_line = append_console_line
        self._append_debug_output_line = append_debug_output_line
        self._apply_debug_inspector_event = apply_debug_inspector_event
        self._refresh_run_action_states = refresh_run_action_states
        self._set_run_status = set_run_status
        self._focus_run_log_tab = focus_run_log_tab
        self._focus_problems_tab = focus_problems_tab
        self._set_debug_command_input_enabled = set_debug_command_input_enabled
        self._clear_controller_active_session_mode = clear_controller_active_session_mode
        self._finalize_run_log = finalize_run_log
        self._update_problems_from_output = update_problems_from_output
        self._auto_open_console_on_run_output_enabled = auto_open_console_on_run_output_enabled
        self._auto_open_problems_on_run_failure_enabled = auto_open_problems_on_run_failure_enabled

    def apply(self, event: ProcessEvent) -> None:
        """Apply one process event to shell output/debug state."""
        if self._is_shutting_down():
            return

        active_mode = self._get_active_session_mode()

        if event.event_type == "output":
            stream = event.stream or "stdout"
            text = event.text or ""
            parsed_debug_event = self._get_debug_session().ingest_output_line(text)
            if parsed_debug_event is not None and parsed_debug_event.event_type in {"paused", "running", "stack"}:
                if parsed_debug_event.message:
                    self._append_debug_output_line(f"[debug] {parsed_debug_event.message}")
                self._apply_debug_inspector_event()
                self._refresh_run_action_states()
                return

            self._append_output_tail(text)
            self._append_console_line(text, stream)
            if self._auto_open_console_on_run_output_enabled():
                self._focus_run_log_tab()
            if active_mode == constants.RUN_MODE_PYTHON_DEBUG:
                for line in text.rstrip().splitlines():
                    self._append_debug_output_line(line)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            if active_mode == constants.RUN_MODE_PYTHON_DEBUG:
                self._get_debug_session().mark_exited()
                self._apply_debug_inspector_event()
            if event.terminated_by_user:
                self._append_console_line(f"Run terminated by user (code={return_code}).\n", "system")
                session_line = f"[system] Session terminated (code={return_code})."
                self._set_run_status("terminated", return_code)
            else:
                self._append_console_line(f"Run finished (code={return_code}).\n", "system")
                session_line = f"[system] Session finished (code={return_code})."
                if return_code == constants.RUN_EXIT_SUCCESS:
                    self._set_run_status("success", return_code)
                else:
                    self._set_run_status("failed", return_code)
            if active_mode == constants.RUN_MODE_PYTHON_DEBUG:
                self._append_debug_output_line(session_line)
            self._set_debug_command_input_enabled(False)

            self._set_active_session_mode(None)
            self._clear_controller_active_session_mode()
            self._refresh_run_action_states()
            self._finalize_run_log(return_code)
            problems = self._update_problems_from_output()
            if (
                not event.terminated_by_user
                and (return_code or 0) != constants.RUN_EXIT_SUCCESS
                and problems
                and self._auto_open_problems_on_run_failure_enabled()
            ):
                self._focus_problems_tab()
            return

        if event.event_type == "state":
            if event.state in {"running", "stopping"}:
                self._set_run_status(event.state)
            self._refresh_run_action_states()
