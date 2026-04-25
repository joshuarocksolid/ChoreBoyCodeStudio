"""Debug command and breakpoint control workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide2.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from app.core import constants
from app.debug.debug_breakpoints import build_breakpoint, breakpoint_key
from app.debug.debug_command_service import (
    evaluate_command,
    expand_variable_command,
    select_frame_command,
    update_breakpoints_command,
    update_exception_policy_command,
)
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy


class DebugControlWorkflow:
    """Owns debug transport commands, breakpoint state, and debug panel actions."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dispatch_debug_transport_command(
        self,
        command_factory: Callable[[], tuple[str, dict[str, object]]],
    ) -> None:
        window = self._window
        if not window._run_service.supervisor.is_running():
            QMessageBox.information(window, "Debug", "No active debug session.")
            return
        command_name, arguments = command_factory()
        self.send_debug_command(command_name, arguments)

    def send_debug_command(self, command_name: str, arguments: dict[str, object] | None = None) -> None:
        window = self._window
        try:
            window._run_service.send_debug_command(command_name, arguments)
        except Exception as exc:
            QMessageBox.warning(window, "Debug", f"Debug command failed: {exc}")
            return
        window._append_debug_output_line("[debug] %s" % (command_name.replace("_", " "),))

    def handle_pause_debug_action(self) -> None:
        window = self._window
        paused, error_message = window._run_session_controller.pause_session(
            append_python_console_line=window._append_python_console_line,
            append_debug_output_line=window._append_debug_output_line,
        )
        if error_message is not None:
            QMessageBox.warning(window, "Debug", f"Pause failed: {error_message}")
        if paused:
            window._refresh_run_action_states()

    def handle_toggle_breakpoint_action(self) -> None:
        window = self._window
        editor_widget = window._active_editor_widget()
        if editor_widget is None:
            QMessageBox.information(window, "Toggle Breakpoint", "Open a Python file first.")
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        editor_widget.toggle_breakpoint(line_number)

    def handle_remove_all_breakpoints_action(self) -> None:
        window = self._window
        window._breakpoints_by_file.clear()
        window._breakpoint_specs_by_key.clear()
        for editor_widget in window._editor_widgets_by_path.values():
            editor_widget.set_breakpoints(set())
        self.refresh_breakpoints_list()
        self.sync_breakpoints_to_active_debug_session()
        window._refresh_run_action_states()

    def handle_editor_breakpoint_toggled(self, file_path: str, line_number: int, enabled: bool) -> None:
        window = self._window
        breakpoints = window._breakpoints_by_file.setdefault(file_path, set())
        if enabled:
            breakpoints.add(line_number)
            self.ensure_breakpoint_spec(file_path, line_number)
        else:
            breakpoints.discard(line_number)
            window._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)
        if not breakpoints:
            window._breakpoints_by_file.pop(file_path, None)
        self.refresh_breakpoints_list()
        self.sync_breakpoints_to_active_debug_session()
        window._refresh_run_action_states()

    def refresh_breakpoints_list(self) -> None:
        window = self._window
        if window._debug_panel is None:
            return
        window._debug_panel.set_breakpoints(self.display_breakpoints())

    def ensure_breakpoint_spec(self, file_path: str, line_number: int) -> DebugBreakpoint:
        window = self._window
        key = breakpoint_key(file_path, line_number)
        existing = window._breakpoint_specs_by_key.get(key)
        if existing is not None:
            return existing
        created = build_breakpoint(file_path=file_path, line_number=line_number)
        window._breakpoint_specs_by_key[key] = created
        return created

    def all_breakpoints(self) -> list[DebugBreakpoint]:
        window = self._window
        breakpoints = list(window._breakpoint_specs_by_key.values())
        return sorted(breakpoints, key=lambda breakpoint: (breakpoint.file_path, breakpoint.line_number))

    def display_breakpoints(self) -> list[DebugBreakpoint]:
        window = self._window
        verified_by_id = {
            breakpoint.breakpoint_id: breakpoint
            for breakpoint in window._debug_session.state.breakpoints
        }
        display_breakpoints: list[DebugBreakpoint] = []
        for breakpoint in self.all_breakpoints():
            verified = verified_by_id.get(breakpoint.breakpoint_id)
            if verified is None:
                display_breakpoints.append(breakpoint)
                continue
            display_breakpoints.append(
                DebugBreakpoint(
                    breakpoint_id=breakpoint.breakpoint_id,
                    file_path=breakpoint.file_path,
                    line_number=breakpoint.line_number,
                    enabled=breakpoint.enabled,
                    condition=breakpoint.condition,
                    hit_condition=breakpoint.hit_condition,
                    verified=verified.verified,
                    verification_message=verified.verification_message,
                )
            )
        return display_breakpoints

    def build_debug_breakpoints_for_launch(
        self,
        *,
        active_file_path: str | None = None,
        remapped_active_path: str | None = None,
    ) -> list[DebugBreakpoint]:
        launch_breakpoints: list[DebugBreakpoint] = []
        for breakpoint in self.all_breakpoints():
            file_path = breakpoint.file_path
            if active_file_path and remapped_active_path and file_path == active_file_path:
                file_path = remapped_active_path
            launch_breakpoints.append(
                DebugBreakpoint(
                    breakpoint_id=breakpoint.breakpoint_id,
                    file_path=file_path,
                    line_number=breakpoint.line_number,
                    enabled=breakpoint.enabled,
                    condition=breakpoint.condition,
                    hit_condition=breakpoint.hit_condition,
                    verified=breakpoint.verified,
                    verification_message=breakpoint.verification_message,
                )
            )
        return launch_breakpoints

    def handle_debug_refresh_stack(self) -> None:
        window = self._window
        if not window._run_service.supervisor.is_running():
            return
        selected_frame = window._debug_session.state.selected_frame
        if selected_frame is None:
            return
        command_name, arguments = select_frame_command(selected_frame.frame_id)
        self.send_debug_command(command_name, arguments)

    def handle_debug_refresh_locals(self) -> None:
        window = self._window
        if not window._run_service.supervisor.is_running():
            return
        selected_frame = window._debug_session.state.selected_frame
        if selected_frame is None:
            return
        command_name, arguments = select_frame_command(selected_frame.frame_id)
        self.send_debug_command(command_name, arguments)

    def handle_debug_navigate_preview(self, file_path: str, line_number: int) -> None:
        if not self.is_debug_navigation_target_allowed(file_path):
            return
        self._window._open_file_at_line(file_path, line_number, preview=True)

    def handle_debug_navigate_permanent(self, file_path: str, line_number: int) -> None:
        if not self.is_debug_navigation_target_allowed(file_path):
            return
        self._window._open_file_at_line(file_path, line_number, preview=False)

    def is_debug_navigation_target_allowed(self, file_path: str) -> bool:
        window = self._window
        if window._loaded_project is None:
            return True
        candidate_path = Path(file_path).expanduser().resolve()
        project_root_path = Path(window._loaded_project.project_root).expanduser().resolve()
        try:
            candidate_path.relative_to(project_root_path)
            return True
        except ValueError:
            return False

    def handle_debug_watch_evaluate(self, expression: str) -> None:
        window = self._window
        if not window._run_service.supervisor.is_running():
            return
        frame_id = 0
        selected_frame = window._debug_session.state.selected_frame
        if selected_frame is not None:
            frame_id = selected_frame.frame_id
        command_name, arguments = evaluate_command(expression, frame_id=frame_id)
        self.send_debug_command(command_name, arguments)

    def handle_debug_command_submit(self, command_text: str) -> None:
        window = self._window
        if not command_text.strip():
            return
        if window._run_session_controller.active_session_mode != constants.RUN_MODE_PYTHON_DEBUG:
            return
        if not window._run_service.supervisor.is_running():
            return
        self.handle_debug_watch_evaluate(command_text.strip())

    def handle_debug_breakpoint_remove(self, file_path: str, line_number: int) -> None:
        window = self._window
        breakpoints = window._breakpoints_by_file.get(file_path, set())
        breakpoints.discard(line_number)
        if not breakpoints:
            window._breakpoints_by_file.pop(file_path, None)
        window._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)
        editor_widget = window._editor_widgets_by_path.get(file_path)
        if editor_widget is not None:
            editor_widget.set_breakpoints(window._breakpoints_by_file.get(file_path, set()))
        self.refresh_breakpoints_list()
        self.sync_breakpoints_to_active_debug_session()
        window._refresh_run_action_states()

    def handle_debug_breakpoint_toggle(self, file_path: str, line_number: int, enabled: bool) -> None:
        window = self._window
        spec = self.ensure_breakpoint_spec(file_path, line_number)
        window._breakpoint_specs_by_key[breakpoint_key(file_path, line_number)] = DebugBreakpoint(
            breakpoint_id=spec.breakpoint_id,
            file_path=spec.file_path,
            line_number=spec.line_number,
            enabled=enabled,
            condition=spec.condition,
            hit_condition=spec.hit_condition,
            verified=spec.verified,
            verification_message=spec.verification_message,
        )
        self.refresh_breakpoints_list()
        self.sync_breakpoints_to_active_debug_session()
        window._refresh_run_action_states()

    def handle_debug_breakpoint_edit(self, file_path: str, line_number: int) -> None:
        window = self._window
        spec = self.ensure_breakpoint_spec(file_path, line_number)
        condition, accepted = QInputDialog.getText(
            window,
            "Breakpoint Condition",
            "Pause only when this expression is truthy (leave blank for always):",
            QLineEdit.Normal,
            spec.condition,
        )
        if not accepted:
            return
        hit_value = spec.hit_condition or 0
        hit_condition, accepted = QInputDialog.getInt(
            window,
            "Breakpoint Hit Count",
            "Pause after this many hits (0 disables threshold):",
            hit_value,
            0,
            999999,
            1,
        )
        if not accepted:
            return
        window._breakpoint_specs_by_key[breakpoint_key(file_path, line_number)] = DebugBreakpoint(
            breakpoint_id=spec.breakpoint_id,
            file_path=spec.file_path,
            line_number=spec.line_number,
            enabled=spec.enabled,
            condition=condition.strip(),
            hit_condition=hit_condition or None,
            verified=spec.verified,
            verification_message=spec.verification_message,
        )
        self.refresh_breakpoints_list()
        self.sync_breakpoints_to_active_debug_session()
        window._refresh_run_action_states()

    def sync_breakpoints_to_active_debug_session(self) -> None:
        window = self._window
        if not (window._run_service.is_debug_mode and window._run_service.is_debug_paused):
            return
        command_name, arguments = update_breakpoints_command(self.all_breakpoints())
        self.send_debug_command(command_name, arguments)

    def handle_debug_exception_settings_action(self) -> None:
        window = self._window
        current_value = "Raised + uncaught" if window._debug_exception_policy.stop_on_raised_exceptions else "Uncaught only"
        if not window._debug_exception_policy.stop_on_uncaught_exceptions:
            current_value = "Disabled"
        selection, accepted = QInputDialog.getItem(
            window,
            "Debug Exception Stops",
            "Pause on exceptions:",
            ["Disabled", "Uncaught only", "Raised + uncaught"],
            ["Disabled", "Uncaught only", "Raised + uncaught"].index(current_value),
            False,
        )
        if not accepted or not selection:
            return
        window._debug_exception_policy = DebugExceptionPolicy(
            stop_on_uncaught_exceptions=selection != "Disabled",
            stop_on_raised_exceptions=selection == "Raised + uncaught",
        )
        if window._run_service.is_debug_mode and window._run_service.is_debug_paused:
            command_name, arguments = update_exception_policy_command(window._debug_exception_policy)
            self.send_debug_command(command_name, arguments)

    def handle_debug_variable_expand(self, variables_reference: int) -> None:
        window = self._window
        if variables_reference <= 0:
            return
        if not window._run_service.supervisor.is_running():
            return
        command_name, arguments = expand_variable_command(variables_reference)
        self.send_debug_command(command_name, arguments)

    def handle_debug_frame_selected(self, frame_id: int) -> None:
        window = self._window
        if frame_id <= 0:
            return
        if not window._run_service.supervisor.is_running():
            return
        command_name, arguments = select_frame_command(frame_id)
        self.send_debug_command(command_name, arguments)
