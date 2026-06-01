"""Debug inspector panel sync and execution-line highlighting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol

from app.debug.debug_models import DebugExecutionState
from app.debug.debug_session import DebugSession
from app.shell.debug_control_workflow import DebugControlWorkflow


class DebugInspectorEditorPort(Protocol):
    """Minimal editor surface for debug execution line highlighting."""

    def set_debug_execution_line(self, line_number: int) -> None:
        ...

    def clear_debug_execution_line(self) -> None:
        ...


class DebugInspectorPanelPort(Protocol):
    """Minimal debug panel surface for output and state sync."""

    def append_output(self, text: str) -> None:
        ...

    def update_from_state(self, state: object) -> None:
        ...


class DebugInspectorWorkflowHost(Protocol):
    """Host ports for :class:`DebugInspectorWorkflow`."""

    @property
    def debug_panel(self) -> DebugInspectorPanelPort | None:
        ...

    @property
    def debug_session(self) -> DebugSession:
        ...

    @property
    def debug_control_workflow(self) -> DebugControlWorkflow:
        ...

    @property
    def editor_widgets_by_path(self) -> Mapping[str, DebugInspectorEditorPort]:
        ...

    @property
    def debug_execution_editor(self) -> DebugInspectorEditorPort | None:
        ...

    @debug_execution_editor.setter
    def debug_execution_editor(self, editor: DebugInspectorEditorPort | None) -> None:
        ...

    def open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        ...


class DebugInspectorWorkflow:
    """Owns debug panel output append and pause/running inspector UI sync."""

    def __init__(self, host: DebugInspectorWorkflowHost) -> None:
        self._host = host

    def append_debug_output_line(self, text: str) -> None:
        panel = self._host.debug_panel
        if panel is None:
            return
        panel.append_output(text)

    def apply_debug_inspector_event(self) -> None:
        panel = self._host.debug_panel
        if panel is None:
            return
        state = self._host.debug_session.state
        panel.update_from_state(state)

        frame = state.selected_frame
        if state.execution_state == DebugExecutionState.PAUSED and frame is not None:
            if not self._host.debug_control_workflow.is_debug_navigation_target_allowed(frame.file_path):
                self.clear_debug_execution_indicator()
                return
            self._host.open_file_at_line(frame.file_path, frame.line_number)
            resolved = str(Path(frame.file_path).expanduser().resolve())
            editor = self._host.editor_widgets_by_path.get(resolved)
            if editor is not None:
                if self._host.debug_execution_editor is not None and self._host.debug_execution_editor is not editor:
                    self.clear_debug_execution_indicator()
                editor.set_debug_execution_line(frame.line_number)
                self._host.debug_execution_editor = editor
        elif state.execution_state in {DebugExecutionState.RUNNING, DebugExecutionState.EXITED}:
            self.clear_debug_execution_indicator()

    def clear_debug_execution_indicator(self) -> None:
        if self._host.debug_execution_editor is None:
            return
        editor = self._host.debug_execution_editor
        self._host.debug_execution_editor = None
        try:
            editor.clear_debug_execution_line()
        except RuntimeError:
            # Widget wrapper may already be invalid while the window is closing.
            return


class MainWindowDebugInspectorHost:
    """Adapts :class:`MainWindow` to :class:`DebugInspectorWorkflowHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def debug_panel(self) -> DebugInspectorPanelPort | None:
        return self._window._debug_panel

    @property
    def debug_session(self) -> DebugSession:
        return self._window._debug_session

    @property
    def debug_control_workflow(self) -> DebugControlWorkflow:
        return self._window._debug_control_workflow

    @property
    def editor_widgets_by_path(self) -> Mapping[str, DebugInspectorEditorPort]:
        return self._window._editor_widgets_by_path

    @property
    def debug_execution_editor(self) -> DebugInspectorEditorPort | None:
        return self._window._debug_execution_editor

    @debug_execution_editor.setter
    def debug_execution_editor(self, editor: DebugInspectorEditorPort | None) -> None:
        self._window._debug_execution_editor = editor

    def open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        self._window._editor_tab_workflow.open_file_at_line(file_path, line_number, preview=preview)
