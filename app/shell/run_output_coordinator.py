"""Coordinator for run/debug output and lifecycle event routing."""

from __future__ import annotations

from typing import Callable, Mapping

from app.core import constants
from app.debug.debug_session import DebugSession
from app.run.exit_status import describe_exit_code
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
        self._finalize_run_log = finalize_run_log
        self._update_problems_from_output = update_problems_from_output
        self._auto_open_console_on_run_output_enabled = auto_open_console_on_run_output_enabled
        self._auto_open_problems_on_run_failure_enabled = auto_open_problems_on_run_failure_enabled

    def apply(self, event: ProcessEvent) -> None:
        """Apply one process event to shell output/debug state."""
        if self._is_shutting_down():
            return

        active_mode = self._get_active_session_mode()

        if event.event_type == "debug":
            payload = event.payload
            if isinstance(payload, Mapping):
                self._get_debug_session().apply_protocol_message(payload)
                message = self._extract_debug_status_line(payload)
                if message:
                    self._append_debug_output_line(message)
                self._apply_debug_inspector_event()
                self._refresh_run_action_states()
            return

        if event.event_type == "output":
            stream = event.stream or "stdout"
            text = event.text or ""
            self._append_output_tail(text)
            self._append_console_line(text, stream)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            exit_detail = describe_exit_code(return_code)
            if active_mode == constants.RUN_MODE_PYTHON_DEBUG:
                self._get_debug_session().mark_exited()
                self._apply_debug_inspector_event()
            if event.terminated_by_user:
                self._append_console_line(f"Run terminated by user ({exit_detail}).\n", "system")
                session_line = f"[system] Session terminated ({exit_detail})."
                self._set_run_status("terminated", return_code)
            else:
                if return_code is not None and return_code < 0:
                    self._append_console_line(
                        f"Run terminated by {exit_detail} -- possible crash in native code.\n",
                        "stderr",
                    )
                    session_line = f"[system] Session terminated by {exit_detail}."
                    self._set_run_status("failed", return_code)
                else:
                    self._append_console_line(f"Run finished ({exit_detail}).\n", "system")
                    session_line = f"[system] Session finished ({exit_detail})."
                    if return_code == constants.RUN_EXIT_SUCCESS:
                        self._set_run_status("success", return_code)
                    else:
                        self._set_run_status("failed", return_code)
            if active_mode == constants.RUN_MODE_PYTHON_DEBUG:
                self._append_debug_output_line(session_line)
            self._set_debug_command_input_enabled(False)

            self._set_active_session_mode(None)
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
                self._set_run_status(event.state, None)
            self._refresh_run_action_states()

    @staticmethod
    def _extract_debug_status_line(payload: Mapping[str, object]) -> str:
        kind = str(payload.get("kind", "")).strip()
        if kind == "event":
            event_name = str(payload.get("event", "")).strip()
            body = payload.get("body")
            if isinstance(body, Mapping):
                message = str(body.get("message", "")).strip()
            else:
                message = ""
            if event_name in {"session_ready", "stopped", "continued", "session_ended"} and message:
                return "[debug] %s" % (message,)
            return ""
        if kind == "response":
            success = bool(payload.get("success", False))
            if success:
                return ""
            error_message = str(payload.get("error_message", "")).strip()
            return "[debug] %s" % (error_message,) if error_message else ""
        return ""
