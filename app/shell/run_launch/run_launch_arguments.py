"""Run-with-arguments dialog orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

from app.core import constants
from app.project.file_inventory import iter_python_files
from app.project.run_configs import RunConfiguration
from app.shell.run_arguments_helpers import normalize_entry_path_for_project
from app.shell.run_configurations_dialog import RunConfigurationsDialog, RunConfigurationsInitial
from app.shell.run_launch.run_configuration_workflow import proposed_new_config_name
from app.shell.run_launch.run_launch_preflight import ensure_run_preflight_ready
from app.shell.run_with_arguments_dialog import (
    RunInvocation,
    RunWithArgumentsDialog,
    RunWithArgumentsInitial,
    RunWithArgumentsOutcomeKind,
)
from app.shell.run_launch.run_launch_workflow_host import RunLaunchWorkflowHost

if TYPE_CHECKING:
    from app.shell.run_launch_workflow import RunLaunchWorkflow


def collect_project_entry_file_choices(project_root: str | None) -> tuple[str, ...]:
    if project_root is None:
        return ()
    root = Path(project_root).expanduser().resolve()
    return tuple(
        sorted(
            candidate.relative_to(root).as_posix()
            for candidate in iter_python_files(root)
            if candidate.is_file()
        )
    )


def build_run_with_arguments_initial(
    host: RunLaunchWorkflowHost,
    *,
    entry_file: str,
    argv: Sequence[str],
    working_directory: str | None,
    env_overrides: Mapping[str, str],
) -> RunWithArgumentsInitial:
    loaded_project = host.loaded_project()
    project_root: str | None = None
    named_configurations: tuple[RunConfiguration, ...] = ()
    entry_choices: tuple[str, ...] = ()

    if loaded_project is not None:
        project_root = loaded_project.project_root
        named_configurations = tuple(host.run_config_controller().load_configs(loaded_project))
        entry_choices = collect_project_entry_file_choices(project_root)

    normalized_entry = normalize_entry_path_for_project(
        entry_file,
        project_root=project_root,
    )

    return RunWithArgumentsInitial(
        entry_file=normalized_entry or entry_file,
        argv=argv,
        working_directory=working_directory,
        env_overrides=env_overrides,
        recent_argv_history=tuple(host.settings_service().load_recent_argv_history()),
        project_root=project_root,
        entry_file_choices=entry_choices,
        named_configurations=named_configurations,
    )


def prompt_run_with_arguments_and_launch(
    workflow: RunLaunchWorkflow,
    *,
    entry_file: str,
    argv: Sequence[str],
    env_overrides: Mapping[str, str],
    working_directory: str | None = None,
) -> bool:
    host = workflow._host
    initial = build_run_with_arguments_initial(
        host,
        entry_file=entry_file,
        argv=argv,
        working_directory=working_directory,
        env_overrides=env_overrides,
    )
    result = RunWithArgumentsDialog.run_dialog(
        host.dialog_parent(),
        initial=initial,
        tokens=host.resolve_theme_tokens(),
    )
    if result.outcome == RunWithArgumentsOutcomeKind.OPEN_CONFIGURATIONS:
        return workflow.handle_run_with_configuration_action()
    if result.outcome != RunWithArgumentsOutcomeKind.RUN or result.invocation is None:
        return False
    invocation = result.invocation
    if invocation.argv_text:
        host.settings_service().push_recent_argv_history(invocation.argv_text)
    return launch_ad_hoc_run_invocation(workflow, invocation)


def launch_ad_hoc_run_invocation(workflow: RunLaunchWorkflow, invocation: RunInvocation) -> bool:
    if invocation.save_request:
        open_save_invocation_as_configuration_dialog(workflow, invocation)
    if not ensure_run_preflight_ready(
        workflow._host,
        title="Run With Arguments",
        entry_file=invocation.entry_file,
        working_directory=invocation.working_directory,
    ):
        return False
    return workflow.start_session(
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        entry_file=invocation.entry_file,
        argv=list(invocation.argv),
        working_directory=invocation.working_directory,
        env_overrides=dict(invocation.env_overrides),
    )


def open_save_invocation_as_configuration_dialog(
    workflow: RunLaunchWorkflow,
    invocation: RunInvocation,
) -> None:
    host = workflow._host
    loaded_project = host.loaded_project()
    if loaded_project is None:
        host.show_information(
            "Save as Configuration",
            "Open a project first to save named run configurations.",
        )
        return
    existing_configs = host.run_config_controller().load_configs(loaded_project)
    proposed_name = proposed_new_config_name(existing_configs)
    new_config = RunConfiguration(
        name=proposed_name,
        entry_file=invocation.entry_file,
        argv=list(invocation.argv),
        working_directory=invocation.working_directory,
        env_overrides=dict(invocation.env_overrides),
    )
    initial = RunConfigurationsInitial(
        configurations=[*existing_configs, new_config],
        default_argv=loaded_project.metadata.default_argv,
        default_entry=loaded_project.metadata.default_entry,
        project_root=loaded_project.project_root,
        active_config_name=host.active_named_run_config_name(),
        initial_selection_name=new_config.name,
    )
    result = RunConfigurationsDialog.run_dialog(
        host.dialog_parent(),
        initial=initial,
        tokens=host.resolve_theme_tokens(),
    )
    if result is None:
        return
    workflow._run_configuration.persist_run_configurations_result(result)
