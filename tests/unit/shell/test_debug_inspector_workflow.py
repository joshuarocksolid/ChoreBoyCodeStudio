"""Unit tests for debug inspector panel sync workflow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.debug.debug_models import DebugExecutionState, DebugFrame, DebugSessionState  # noqa: E402
from app.shell.debug_inspector_workflow import DebugInspectorWorkflow  # noqa: E402
from tests.support.shell_host_stubs import StubDebugShellHost, debug_control_workflow  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeDebugPanel:
    def __init__(self) -> None:
        self.state_updates: list[DebugSessionState] = []

    def append_output(self, text: str) -> None:
        return None

    def update_from_state(self, state: DebugSessionState) -> None:
        self.state_updates.append(state)


class _FakeEditorWidget:
    def __init__(self, *, clear_raises: bool = False) -> None:
        self.clear_calls = 0
        self._clear_raises = clear_raises

    def clear_debug_execution_line(self) -> None:
        self.clear_calls += 1
        if self._clear_raises:
            raise RuntimeError("widget already deleted")

    def set_debug_execution_line(self, line_number: int) -> None:
        return None


class _FakeDebugInspectorHost:
    def __init__(self) -> None:
        self.debug_panel = _FakeDebugPanel()
        self.loaded_project = SimpleNamespace(project_root="/tmp/project")
        self.debug_execution_editor: _FakeEditorWidget | None = None
        self.editor_widgets_by_path: dict[str, _FakeEditorWidget] = {}
        self.open_calls: list[tuple[str, int | None]] = []
        self.debug_control_workflow = debug_control_workflow(
            StubDebugShellHost(_loaded_project=self.loaded_project)
        )
        self.debug_session = SimpleNamespace(
            state=DebugSessionState(
                execution_state=DebugExecutionState.PAUSED,
                frames=[
                    DebugFrame(
                        file_path="/tmp/ide/app/runner/runner_main.py",
                        line_number=58,
                        function_name="_run_entry_script",
                    )
                ],
            )
        )

    def open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        self.open_calls.append((file_path, line_number))


def test_apply_debug_inspector_event_ignores_non_project_paused_frame_navigation() -> None:
    host = _FakeDebugInspectorHost()
    workflow = DebugInspectorWorkflow(host)

    workflow.apply_debug_inspector_event()

    assert host.open_calls == []


def test_clear_debug_execution_indicator_handles_deleted_editor_wrapper() -> None:
    host = _FakeDebugInspectorHost()
    host.debug_execution_editor = _FakeEditorWidget(clear_raises=True)
    workflow = DebugInspectorWorkflow(host)

    workflow.clear_debug_execution_indicator()

    assert host.debug_execution_editor is None
