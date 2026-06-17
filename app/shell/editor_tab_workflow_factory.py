"""Constructs sub-workflows for :class:`EditorTabWorkflow`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editors.editor_manager import EditorManager
from app.shell.editor_tab_bindings_workflow import EditorTabBindingsWorkflow
from app.shell.editor_tab_buffer_workflow import EditorTabBufferWorkflow
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost
from app.shell.editor_tab_lifecycle_workflow import EditorTabLifecycleWorkflow
from app.shell.editor_tab_markdown_workflow import EditorTabMarkdownWorkflow
from app.shell.editor_tab_outline_workflow import EditorTabOutlineWorkflow
from app.shell.editor_tab_poll_workflow import EditorTabPollWorkflow
from app.shell.editor_tab_preferences_workflow import EditorTabPreferencesWorkflow
from app.shell.editor_latency_recorder import EditorLatencyRecorder
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.external_file_change_workflow import ExternalFileChangeWorkflow
from app.shell.markdown_tab_registry import MarkdownTabRegistry
from app.shell.editor_sync_workflow import EditorSyncWorkflow


@dataclass(frozen=True)
class EditorTabSubworkflows:
    bindings_workflow: EditorTabBindingsWorkflow
    markdown_registry: MarkdownTabRegistry
    preferences_workflow: EditorTabPreferencesWorkflow
    poll_workflow: EditorTabPollWorkflow
    outline_workflow: EditorTabOutlineWorkflow
    markdown_workflow: EditorTabMarkdownWorkflow
    buffer_workflow: EditorTabBufferWorkflow
    lifecycle_workflow: EditorTabLifecycleWorkflow
    latency_recorder: EditorLatencyRecorder


def create_editor_tab_subworkflows(
    *,
    host: EditorTabWorkflowHost,
    editor_manager: EditorManager,
    editor_tabs_coordinator: EditorTabsCoordinator,
    save_workflow: Any,
    debug_control_workflow: Any,
    external_file_change_workflow: ExternalFileChangeWorkflow,
    editor_sync_workflow: EditorSyncWorkflow,
    tab_workflow: Any,
    refresh_markdown_action_states: Any,
) -> EditorTabSubworkflows:
    markdown_registry = MarkdownTabRegistry(host.markdown_panes_by_path())
    preferences_workflow = EditorTabPreferencesWorkflow(
        host=host,
        editor_manager=editor_manager,
        editor_widgets_by_path=host.editor_widgets_by_path,
        status_controller=host.status_controller,
        loaded_project=host.loaded_project,
    )
    outline_workflow = EditorTabOutlineWorkflow(
        host=host,
        editor_manager=editor_manager,
        editor_widgets_by_path=host.editor_widgets_by_path,
        editor_tab_factory=host.editor_tab_factory(),
        buffer_revision=editor_tabs_coordinator.buffer_revision,
    )
    markdown_workflow = EditorTabMarkdownWorkflow(
        host=host,
        editor_manager=editor_manager,
        markdown_registry=markdown_registry,
        refresh_markdown_action_states=refresh_markdown_action_states,
    )
    return EditorTabSubworkflows(
        bindings_workflow=EditorTabBindingsWorkflow(),
        markdown_registry=markdown_registry,
        preferences_workflow=preferences_workflow,
        poll_workflow=EditorTabPollWorkflow(
            host=host,
            editor_manager=editor_manager,
            editor_sync_workflow=editor_sync_workflow,
            external_file_change_workflow=external_file_change_workflow,
            refresh_save_action_states=host.refresh_save_action_states,
        ),
        outline_workflow=outline_workflow,
        markdown_workflow=markdown_workflow,
        buffer_workflow=EditorTabBufferWorkflow(
            host=host,
            editor_manager=editor_manager,
            editor_tabs_coordinator=editor_tabs_coordinator,
            outline_workflow=outline_workflow,
            markdown_workflow=markdown_workflow,
            tab_workflow=tab_workflow,
        ),
        lifecycle_workflow=EditorTabLifecycleWorkflow(
            host=host,
            editor_manager=editor_manager,
            editor_tabs_coordinator=editor_tabs_coordinator,
            save_workflow=save_workflow,
            debug_control_workflow=debug_control_workflow,
            markdown_registry=markdown_registry,
            markdown_workflow=markdown_workflow,
            tab_workflow=tab_workflow,
        ),
        latency_recorder=EditorLatencyRecorder(),
    )


__all__ = ["EditorTabSubworkflows", "create_editor_tab_subworkflows"]
