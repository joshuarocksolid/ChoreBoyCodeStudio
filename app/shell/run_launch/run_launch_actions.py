"""Project and named-configuration run/debug launch actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from app.core import constants
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy
from app.project.run_configs import RunConfiguration
from app.shell.run_configurations_dialog import RunConfigurationsDialog, RunConfigurationsInitial
from app.shell.run_launch.debug_targets import ProjectTarget
from app.shell.run_launch.run_launch_arguments import prompt_run_with_arguments_and_launch
from app.shell.run_launch.run_launch_preflight import ensure_run_preflight_ready

if TYPE_CHECKING:
    from app.shell.run_launch_workflow import RunLaunchWorkflow


def launch_run_configuration(
    workflow: RunLaunchWorkflow,
    config: RunConfiguration,
    *,
    debug: bool,
) -> bool:
    mode = constants.RUN_MODE_PYTHON_DEBUG if debug else constants.RUN_MODE_PYTHON_SCRIPT
    title = (
        f"Debug Configuration: {config.name}" if debug else f"Run Configuration: {config.name}"
    )
    if not ensure_run_preflight_ready(
        workflow._host,
        title=title,
        entry_file=config.entry_file,
        working_directory=config.working_directory,
        config_name=config.name,
    ):
        return False
    breakpoints: list[DebugBreakpoint] | None = None
    debug_exception_policy: DebugExceptionPolicy | None = None
    if debug:
        breakpoints = workflow._host.debug_control_workflow().build_debug_breakpoints_for_launch()
        debug_exception_policy = workflow._host.debug_exception_policy()
    started = workflow.start_session(
        mode=mode,
        entry_file=config.entry_file,
        argv=list(config.argv),
        working_directory=config.working_directory,
        env_overrides=dict(config.env_overrides),
        breakpoints=breakpoints,
        debug_exception_policy=debug_exception_policy,
    )
    if started and debug:
        workflow.record_debug_target(ProjectTarget())
    return started


def handle_run_project_action(workflow: RunLaunchWorkflow) -> bool:
    loaded_project = workflow._host.loaded_project()
    if loaded_project is None:
        workflow._host.show_warning("Run unavailable", "Open a project before running.")
        return False
    active_config = workflow._run_configuration.resolve_active_named_run_config()
    if active_config is not None:
        return launch_run_configuration(workflow, active_config, debug=False)
    entry_file = (loaded_project.metadata.default_entry or "").strip()
    if not ensure_run_preflight_ready(
        workflow._host,
        title="Run Project",
        entry_file=entry_file,
    ):
        return False
    return workflow.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=entry_file)


def handle_debug_project_action(workflow: RunLaunchWorkflow) -> bool:
    loaded_project = workflow._host.loaded_project()
    if loaded_project is None:
        workflow._host.show_warning("Run unavailable", "Open a project before running.")
        return False
    active_config = workflow._run_configuration.resolve_active_named_run_config()
    if active_config is not None:
        return launch_run_configuration(workflow, active_config, debug=True)
    entry_file = (loaded_project.metadata.default_entry or "").strip()
    if not ensure_run_preflight_ready(
        workflow._host,
        title="Debug Project",
        entry_file=entry_file,
    ):
        return False
    started = workflow.start_session(
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        entry_file=entry_file,
        breakpoints=workflow._host.debug_control_workflow().build_debug_breakpoints_for_launch(),
        debug_exception_policy=workflow._host.debug_exception_policy(),
    )
    if started:
        workflow.record_debug_target(ProjectTarget())
    return started


def handle_run_with_configuration_action(workflow: RunLaunchWorkflow) -> bool:
    loaded_project = workflow._host.loaded_project()
    if loaded_project is None:
        workflow._host.show_warning("Run Configurations", "Open a project first.")
        return False
    existing_configs = workflow._host.run_config_controller().load_configs(loaded_project)
    initial = RunConfigurationsInitial(
        configurations=existing_configs,
        default_argv=loaded_project.metadata.default_argv,
        default_entry=loaded_project.metadata.default_entry,
        project_root=loaded_project.project_root,
        active_config_name=workflow._host.active_named_run_config_name(),
        initial_selection_name=workflow._host.active_named_run_config_name(),
    )
    result = RunConfigurationsDialog.run_dialog(
        workflow._host.dialog_parent(),
        initial=initial,
        tokens=workflow._host.resolve_theme_tokens(),
    )
    if result is None:
        return False
    persisted = workflow._run_configuration.persist_run_configurations_result(result)
    if not persisted:
        return False
    selected_name = result.selected_config_name
    if not selected_name:
        return True
    target = next(
        (config for config in result.configurations if config.name == selected_name),
        None,
    )
    if target is None:
        return True
    return launch_run_configuration(workflow, target, debug=False)


def handle_run_with_arguments_action(workflow: RunLaunchWorkflow) -> bool:
    loaded_project = workflow._host.loaded_project()
    active_tab = workflow._host.editor_manager().active_tab()
    active_file_path: str | None = None
    if active_tab is not None and getattr(active_tab, "file_path", None):
        active_file_path = active_tab.file_path
    default_entry = ""
    default_argv: Sequence[str] = ()
    default_env: Mapping[str, str] = {}
    if loaded_project is not None:
        default_entry = (loaded_project.metadata.default_entry or "").strip()
        default_argv = tuple(loaded_project.metadata.default_argv)
        default_env = dict(loaded_project.metadata.env_overrides)

    initial_entry = active_file_path or default_entry
    return prompt_run_with_arguments_and_launch(
        workflow,
        entry_file=initial_entry,
        argv=default_argv,
        env_overrides=default_env,
    )


def handle_run_active_configuration_action(workflow: RunLaunchWorkflow) -> bool:
    active_config = workflow._run_configuration.resolve_active_named_run_config()
    if active_config is None:
        return handle_run_project_action(workflow)
    return launch_run_configuration(workflow, active_config, debug=False)
