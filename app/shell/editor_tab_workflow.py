"""Editor tab lifecycle façade delegating to focused sub-workflows."""

from __future__ import annotations

from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.shell.editor_tab_bindings_workflow import EditorTabBindingsHost
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost
from app.shell.editor_tab_workflow_factory import create_editor_tab_subworkflows
from app.shell.editor_tab_workflow_mixins import (
    EditorTabBufferDelegates,
    EditorTabLifecycleDelegates,
    EditorTabMarkdownDelegates,
    EditorTabOutlineDelegates,
    EditorTabPollDelegates,
    EditorTabPreferencesDelegates,
)
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.external_file_change_workflow import ExternalFileChangeWorkflow
from app.shell.main_window_editor_tab_host import MainWindowEditorTabHost
from app.shell.editor_sync_factory import build_editor_sync_workflow


class EditorTabWorkflow(
    EditorTabOutlineDelegates,
    EditorTabMarkdownDelegates,
    EditorTabBufferDelegates,
    EditorTabLifecycleDelegates,
    EditorTabPreferencesDelegates,
    EditorTabPollDelegates,
):
    """Thin façade for editor tab lifecycle, buffer sync, markdown, and preferences."""

    def __init__(
        self,
        *,
        host: EditorTabWorkflowHost,
        editor_manager: EditorManager,
        editor_tabs_coordinator: EditorTabsCoordinator,
        save_workflow: Any,
        debug_control_workflow: Any,
        external_file_change_workflow: ExternalFileChangeWorkflow,
        editor_sync_workflow: Any,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._debug_control_workflow = debug_control_workflow
        subworkflows = create_editor_tab_subworkflows(
            host=host,
            editor_manager=editor_manager,
            editor_tabs_coordinator=editor_tabs_coordinator,
            save_workflow=save_workflow,
            debug_control_workflow=debug_control_workflow,
            external_file_change_workflow=external_file_change_workflow,
            editor_sync_workflow=editor_sync_workflow,
            tab_workflow=self,
            refresh_markdown_action_states=self.refresh_markdown_action_states,
        )
        self._bindings_workflow = subworkflows.bindings_workflow
        self._preferences_workflow = subworkflows.preferences_workflow
        self._poll_workflow = subworkflows.poll_workflow
        self._outline_workflow = subworkflows.outline_workflow
        self._markdown_workflow = subworkflows.markdown_workflow
        self._buffer_workflow = subworkflows.buffer_workflow
        self._lifecycle_workflow = subworkflows.lifecycle_workflow
        self._latency_recorder = subworkflows.latency_recorder

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager
        self._preferences_workflow.set_editor_manager(editor_manager)
        self._poll_workflow.set_editor_manager(editor_manager)
        self._outline_workflow.set_editor_manager(editor_manager)
        self._markdown_workflow.set_editor_manager(editor_manager)
        self._buffer_workflow.set_editor_manager(editor_manager)
        self._lifecycle_workflow.set_editor_manager(editor_manager)

    def attach_editor_bindings(
        self, host: EditorTabBindingsHost, editor_widget: CodeEditorWidget, file_path: str
    ) -> None:
        self._bindings_workflow.attach(
            host, editor_widget, file_path, tab_workflow=self, debug_control_workflow=self._debug_control_workflow
        )


def build_editor_tab_workflow(window: Any) -> EditorTabWorkflow:
    """Construct :class:`EditorTabWorkflow` for a ``MainWindow`` instance."""
    return EditorTabWorkflow(
        host=MainWindowEditorTabHost(window),
        editor_manager=window._editor_manager,
        editor_tabs_coordinator=window._editor_tabs_coordinator,
        save_workflow=window._save_workflow,
        debug_control_workflow=window._debug_control_workflow,
        external_file_change_workflow=window._external_file_change_workflow,
        editor_sync_workflow=build_editor_sync_workflow(window),
    )


__all__ = ["EditorTabWorkflow", "EditorTabWorkflowHost", "MainWindowEditorTabHost", "build_editor_tab_workflow"]
