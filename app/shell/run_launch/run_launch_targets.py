"""Rerun-last-debug-target and project-tree run handlers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from app.core import constants
from app.shell.run_launch.debug_targets import (
    ActiveFileTarget,
    CurrentTestTarget,
    ProjectTarget,
    TestNodeTarget,
)
from app.shell.run_launch.run_launch_arguments import prompt_run_with_arguments_and_launch

if TYPE_CHECKING:
    from app.shell.run_launch_workflow import RunLaunchWorkflow


def handle_rerun_last_debug_target_action(workflow: RunLaunchWorkflow) -> None:
    target = workflow.last_debug_target
    if target is None:
        workflow._host.show_information(
            "Rerun Last Debug Target",
            "No previous debug target is available yet.",
        )
        return
    if isinstance(target, ProjectTarget):
        workflow.handle_debug_project_action()
        return
    if isinstance(target, ActiveFileTarget):
        if not workflow._host.editor_tab_factory().open_file_in_editor(target.file_path, preview=False):
            workflow._host.show_warning(
                "Rerun Last Debug Target",
                "The previous debug file could not be reopened.",
            )
            return
        tabs_widget = workflow._host.editor_tabs_widget()
        if tabs_widget is not None:
            index = workflow._host.tab_index_for_path(target.file_path)
            if index >= 0:
                tabs_widget.setCurrentIndex(index)
        workflow.handle_debug_action()
        return
    if isinstance(target, CurrentTestTarget):
        file_path = target.target_path
        if file_path and workflow._host.editor_tab_factory().open_file_in_editor(file_path, preview=False):
            tabs_widget = workflow._host.editor_tabs_widget()
            if tabs_widget is not None:
                index = workflow._host.tab_index_for_path(file_path)
                if index >= 0:
                    tabs_widget.setCurrentIndex(index)
        workflow._host.test_runner_workflow().debug_current_file_tests()
        return
    if isinstance(target, TestNodeTarget):
        workflow._host.test_runner_workflow().debug_test_node(target.node_id)


def handle_tree_run_file(workflow: RunLaunchWorkflow, absolute_path: str) -> bool:
    entry_path = Path(absolute_path).expanduser().resolve()
    if entry_path.suffix.lower() != ".py":
        return False
    return workflow.start_session(
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        entry_file=str(entry_path),
    )


def handle_tree_run_file_with_arguments(workflow: RunLaunchWorkflow, absolute_path: str) -> bool:
    entry_path = Path(absolute_path).expanduser().resolve()
    if entry_path.suffix.lower() != ".py":
        return False
    loaded_project = workflow._host.loaded_project()
    default_env: Mapping[str, str] = (
        dict(loaded_project.metadata.env_overrides)
        if loaded_project is not None
        else {}
    )
    return prompt_run_with_arguments_and_launch(
        workflow,
        entry_file=str(entry_path),
        argv=(),
        env_overrides=default_env,
    )
