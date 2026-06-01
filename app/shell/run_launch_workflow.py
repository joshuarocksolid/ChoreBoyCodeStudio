"""Run and debug launch orchestration for the shell."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from PySide2.QtWidgets import QWidget

from app.core import constants
from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.project.file_inventory import iter_python_files
from app.project.run_configs import RunConfiguration
from app.shell.run_config_controller import RunConfigController
from app.shell.run_configurations_dialog import RunConfigurationsDialog, RunConfigurationsInitial, RunConfigurationsResult
from app.shell.run_launch.active_file_launch import ActiveFileLaunchWorkflow
from app.shell.run_launch.debug_targets import (
    ActiveFileTarget,
    CurrentTestTarget,
    DebugTarget,
    ProjectTarget,
    TestNodeTarget,
    debug_target_from_mapping,
)
from app.shell.run_launch.run_configuration_workflow import RunConfigurationWorkflow, proposed_new_config_name
from app.shell.run_with_arguments_dialog import (
    RunInvocation,
    RunWithArgumentsDialog,
    RunWithArgumentsInitial,
    RunWithArgumentsOutcomeKind,
    RunWithArgumentsResult,
)
from app.shell.run_arguments_helpers import normalize_entry_path_for_project
from app.support.preflight import build_run_preflight


def _collect_project_entry_file_choices(project_root: str | None) -> tuple[str, ...]:
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


def _build_run_with_arguments_initial(
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
        entry_choices = _collect_project_entry_file_choices(project_root)

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

# Re-export debug target types for backward-compatible imports.
__all__ = [
    "ActiveFileTarget",
    "CurrentTestTarget",
    "DebugTarget",
    "ProjectTarget",
    "RunLaunchWorkflow",
    "RunLaunchWorkflowHost",
    "TestNodeTarget",
    "debug_target_from_mapping",
]


class RunLaunchWorkflowHost(Protocol):
    """Host ports for :class:`RunLaunchWorkflow`."""

    def dialog_parent(self) -> QWidget:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def set_loaded_project(self, project: LoadedProject) -> None:
        ...

    def active_named_run_config_name(self) -> str | None:
        ...

    def set_active_named_run_config_name(self, name: str | None) -> None:
        ...

    def editor_manager(self) -> Any:
        ...

    def debug_control_workflow(self) -> Any:
        ...

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        ...

    def run_config_controller(self) -> RunConfigController:
        ...

    def run_debug_presenter(self) -> Any:
        ...

    def settings_service(self) -> Any:
        ...

    def resolve_theme_tokens(self) -> Any:
        ...

    def show_run_preflight_result(self, title: str, summary: str, issues: list[Any]) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def editor_tab_factory(self) -> Any:
        ...

    def editor_tabs_widget(self) -> Any | None:
        ...

    def tab_index_for_path(self, file_path: str) -> int:
        ...

    def test_runner_workflow(self) -> Any:
        ...

    def active_transient_entry_file_path(self) -> str | None:
        ...

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        ...

    def status_bar(self) -> Any:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...

    def show_information(self, title: str, message: str) -> None:
        ...

    def logger(self) -> Any:
        ...


class RunLaunchWorkflow:
    """Owns run/debug launch actions, run-configuration UX, and debug-target memory."""

    def __init__(self, host: RunLaunchWorkflowHost) -> None:
        self._host = host
        self._last_debug_target: DebugTarget | None = None
        self._active_file_launch = ActiveFileLaunchWorkflow(host)
        self._run_configuration = RunConfigurationWorkflow(_RunConfigurationHostAdapter(self))

    @property
    def last_debug_target(self) -> DebugTarget | None:
        return self._last_debug_target

    def has_rerun_target(self) -> bool:
        return self._last_debug_target is not None

    def record_debug_target(self, target: DebugTarget) -> None:
        self._last_debug_target = target

    def record_debug_target_from_dict(self, payload: Mapping[str, object]) -> None:
        parsed = debug_target_from_mapping(payload)
        if parsed is not None:
            self._last_debug_target = parsed

    def start_session(
        self,
        *,
        mode: str,
        entry_file: str | None = None,
        argv: list[str] | None = None,
        working_directory: str | None = None,
        env_overrides: dict[str, str] | None = None,
        breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
        debug_exception_policy: DebugExceptionPolicy | None = None,
        source_maps: list[DebugSourceMap] | None = None,
        skip_save: bool = False,
    ) -> bool:
        return self._host.run_debug_presenter().start_session(
            mode=mode,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            skip_save=skip_save,
        )

    def handle_run_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    def handle_debug_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_DEBUG)

    def handle_run_project_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run unavailable", "Open a project before running.")
            return False
        active_config = self._run_configuration.resolve_active_named_run_config()
        if active_config is not None:
            return self._launch_run_configuration(active_config, debug=False)
        entry_file = (loaded_project.metadata.default_entry or "").strip()
        if not self._ensure_run_preflight_ready(title="Run Project", entry_file=entry_file):
            return False
        return self.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=entry_file)

    def handle_debug_project_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run unavailable", "Open a project before running.")
            return False
        active_config = self._run_configuration.resolve_active_named_run_config()
        if active_config is not None:
            return self._launch_run_configuration(active_config, debug=True)
        entry_file = (loaded_project.metadata.default_entry or "").strip()
        if not self._ensure_run_preflight_ready(title="Debug Project", entry_file=entry_file):
            return False
        started = self.start_session(
            mode=constants.RUN_MODE_PYTHON_DEBUG,
            entry_file=entry_file,
            breakpoints=self._host.debug_control_workflow().build_debug_breakpoints_for_launch(),
            debug_exception_policy=self._host.debug_exception_policy(),
        )
        if started:
            self.record_debug_target(ProjectTarget())
        return started

    def handle_run_with_configuration_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run Configurations", "Open a project first.")
            return False
        existing_configs = self._host.run_config_controller().load_configs(loaded_project)
        initial = RunConfigurationsInitial(
            configurations=existing_configs,
            default_argv=loaded_project.metadata.default_argv,
            default_entry=loaded_project.metadata.default_entry,
            project_root=loaded_project.project_root,
            active_config_name=self._host.active_named_run_config_name(),
            initial_selection_name=self._host.active_named_run_config_name(),
        )
        result = RunConfigurationsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if result is None:
            return False
        persisted = self._run_configuration.persist_run_configurations_result(result)
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
        return self._launch_run_configuration(target, debug=False)

    def handle_run_with_arguments_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        active_tab = self._host.editor_manager().active_tab()
        active_file_path: str | None = None
        if active_tab is not None and getattr(active_tab, "file_path", None):
            active_file_path = active_tab.file_path
        default_entry = ""
        default_argv: tuple[str, ...] = ()
        default_env: Mapping[str, str] = {}
        if loaded_project is not None:
            default_entry = (loaded_project.metadata.default_entry or "").strip()
            default_argv = tuple(loaded_project.metadata.default_argv)
            default_env = dict(loaded_project.metadata.env_overrides)

        initial_entry = active_file_path or default_entry
        return self._prompt_run_with_arguments_and_launch(
            entry_file=initial_entry,
            argv=default_argv,
            env_overrides=default_env,
        )

    def _prompt_run_with_arguments_and_launch(
        self,
        *,
        entry_file: str,
        argv: Sequence[str],
        env_overrides: Mapping[str, str],
        working_directory: str | None = None,
    ) -> bool:
        initial = _build_run_with_arguments_initial(
            self._host,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
        )
        result = RunWithArgumentsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if result.outcome == RunWithArgumentsOutcomeKind.OPEN_CONFIGURATIONS:
            return self.handle_run_with_configuration_action()
        if result.outcome != RunWithArgumentsOutcomeKind.RUN or result.invocation is None:
            return False
        invocation = result.invocation
        if invocation.argv_text:
            self._host.settings_service().push_recent_argv_history(invocation.argv_text)
        return self.launch_ad_hoc_run_invocation(invocation)

    def launch_ad_hoc_run_invocation(self, invocation: RunInvocation) -> bool:
        if invocation.save_request:
            self._open_save_invocation_as_configuration_dialog(invocation)
        if not self._ensure_run_preflight_ready(
            title="Run With Arguments",
            entry_file=invocation.entry_file,
            working_directory=invocation.working_directory,
        ):
            return False
        return self.start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=invocation.entry_file,
            argv=list(invocation.argv),
            working_directory=invocation.working_directory,
            env_overrides=dict(invocation.env_overrides),
        )

    def handle_run_active_configuration_action(self) -> bool:
        active_config = self._run_configuration.resolve_active_named_run_config()
        if active_config is None:
            return self.handle_run_project_action()
        return self._launch_run_configuration(active_config, debug=False)

    def handle_rerun_last_debug_target_action(self) -> None:
        target = self._last_debug_target
        if target is None:
            self._host.show_information(
                "Rerun Last Debug Target",
                "No previous debug target is available yet.",
            )
            return
        if isinstance(target, ProjectTarget):
            self.handle_debug_project_action()
            return
        if isinstance(target, ActiveFileTarget):
            if not self._host.editor_tab_factory().open_file_in_editor(target.file_path, preview=False):
                self._host.show_warning(
                    "Rerun Last Debug Target",
                    "The previous debug file could not be reopened.",
                )
                return
            tabs_widget = self._host.editor_tabs_widget()
            if tabs_widget is not None:
                index = self._host.tab_index_for_path(target.file_path)
                if index >= 0:
                    tabs_widget.setCurrentIndex(index)
            self.handle_debug_action()
            return
        if isinstance(target, CurrentTestTarget):
            file_path = target.target_path
            if file_path and self._host.editor_tab_factory().open_file_in_editor(file_path, preview=False):
                tabs_widget = self._host.editor_tabs_widget()
                if tabs_widget is not None:
                    index = self._host.tab_index_for_path(file_path)
                    if index >= 0:
                        tabs_widget.setCurrentIndex(index)
            self._host.test_runner_workflow().debug_current_file_tests()
            return
        if isinstance(target, TestNodeTarget):
            self._host.test_runner_workflow().debug_test_node(target.node_id)

    def handle_tree_run_file(self, absolute_path: str) -> bool:
        entry_path = Path(absolute_path).expanduser().resolve()
        if entry_path.suffix.lower() != ".py":
            return False
        return self.start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=str(entry_path),
        )

    def handle_tree_run_file_with_arguments(self, absolute_path: str) -> bool:
        entry_path = Path(absolute_path).expanduser().resolve()
        if entry_path.suffix.lower() != ".py":
            return False
        loaded_project = self._host.loaded_project()
        default_env: Mapping[str, str] = (
            dict(loaded_project.metadata.env_overrides)
            if loaded_project is not None
            else {}
        )
        return self._prompt_run_with_arguments_and_launch(
            entry_file=str(entry_path),
            argv=(),
            env_overrides=default_env,
        )

    def install_active_run_config_indicator(self) -> None:
        self._run_configuration.install_active_run_config_indicator()

    def refresh_active_run_config_indicator(self) -> None:
        self._run_configuration.refresh_active_run_config_indicator()

    def _ensure_run_preflight_ready(
        self,
        *,
        title: str,
        entry_file: str,
        working_directory: str | None = None,
        config_name: str | None = None,
    ) -> bool:
        result = build_run_preflight(
            loaded_project=self._host.loaded_project(),
            entry_file=entry_file,
            working_directory=working_directory,
            config_name=config_name,
        )
        if result.is_ready:
            return True
        self._host.show_run_preflight_result(title, result.summary, result.issues)
        return False

    def _launch_run_configuration(
        self,
        config: RunConfiguration,
        *,
        debug: bool,
    ) -> bool:
        mode = constants.RUN_MODE_PYTHON_DEBUG if debug else constants.RUN_MODE_PYTHON_SCRIPT
        title = (
            f"Debug Configuration: {config.name}" if debug else f"Run Configuration: {config.name}"
        )
        if not self._ensure_run_preflight_ready(
            title=title,
            entry_file=config.entry_file,
            working_directory=config.working_directory,
            config_name=config.name,
        ):
            return False
        breakpoints: list[DebugBreakpoint] | None = None
        debug_exception_policy: DebugExceptionPolicy | None = None
        if debug:
            breakpoints = self._host.debug_control_workflow().build_debug_breakpoints_for_launch()
            debug_exception_policy = self._host.debug_exception_policy()
        started = self.start_session(
            mode=mode,
            entry_file=config.entry_file,
            argv=list(config.argv),
            working_directory=config.working_directory,
            env_overrides=dict(config.env_overrides),
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
        )
        if started and debug:
            self.record_debug_target(ProjectTarget())
        return started

    def _open_save_invocation_as_configuration_dialog(self, invocation: RunInvocation) -> None:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_information(
                "Save as Configuration",
                "Open a project first to save named run configurations.",
            )
            return
        existing_configs = self._host.run_config_controller().load_configs(loaded_project)
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
            active_config_name=self._host.active_named_run_config_name(),
            initial_selection_name=new_config.name,
        )
        result = RunConfigurationsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if result is None:
            return
        self._run_configuration.persist_run_configurations_result(result)

    def _start_active_file_session(self, *, mode: str) -> bool:
        return self._active_file_launch.start_active_file_session(
            mode=mode,
            start_session=self.start_session,
            record_debug_target=lambda file_path: self.record_debug_target(
                ActiveFileTarget(file_path=file_path)
            ),
        )

    def delete_transient_entry_file(self, path: str) -> None:
        self._active_file_launch.delete_transient_entry_file(path)


class _RunConfigurationHostAdapter:
    """Adapt :class:`RunLaunchWorkflowHost` to :class:`RunConfigurationHost`."""

    def __init__(self, workflow: RunLaunchWorkflow) -> None:
        self._workflow = workflow

    def dialog_parent(self) -> QWidget:
        return self._workflow._host.dialog_parent()

    def status_bar(self) -> Any:
        return self._workflow._host.status_bar()

    def loaded_project(self) -> LoadedProject | None:
        return self._workflow._host.loaded_project()

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._workflow._host.set_loaded_project(project)

    def active_named_run_config_name(self) -> str | None:
        return self._workflow._host.active_named_run_config_name()

    def set_active_named_run_config_name(self, name: str | None) -> None:
        self._workflow._host.set_active_named_run_config_name(name)

    def run_config_controller(self) -> RunConfigController:
        return self._workflow._host.run_config_controller()

    def resolve_theme_tokens(self) -> Any:
        return self._workflow._host.resolve_theme_tokens()

    def refresh_run_action_states(self) -> None:
        self._workflow._host.refresh_run_action_states()

    def show_warning(self, title: str, message: str) -> None:
        self._workflow._host.show_warning(title, message)

    def handle_run_with_arguments_action(self) -> bool:
        return self._workflow.handle_run_with_arguments_action()

    def handle_run_with_configuration_action(self) -> bool:
        return self._workflow.handle_run_with_configuration_action()
