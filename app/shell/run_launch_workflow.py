"""Run and debug launch orchestration for the shell."""

from __future__ import annotations

from typing import Mapping

from app.core import constants
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.shell.run_launch.active_file_launch import ActiveFileLaunchWorkflow
from app.shell.run_launch.debug_targets import (
    ActiveFileTarget,
    DebugTarget,
    debug_target_from_mapping,
)
from app.shell.run_launch import run_launch_actions, run_launch_targets
from app.shell.run_launch.run_configuration_host_adapter import RunConfigurationHostAdapter
from app.shell.run_launch.run_configuration_workflow import RunConfigurationWorkflow
from app.shell.run_launch.run_launch_arguments import launch_ad_hoc_run_invocation
from app.shell.run_launch.run_launch_workflow_host import RunLaunchWorkflowHost
from app.shell.run_with_arguments_dialog import RunInvocation


class RunLaunchWorkflow:
    """Owns run/debug launch actions, run-configuration UX, and debug-target memory."""

    def __init__(self, host: RunLaunchWorkflowHost) -> None:
        self._host = host
        self._last_debug_target: DebugTarget | None = None
        self._active_file_launch = ActiveFileLaunchWorkflow(host)
        self._run_configuration = RunConfigurationWorkflow(RunConfigurationHostAdapter(self))

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
        return run_launch_actions.handle_run_project_action(self)

    def handle_debug_project_action(self) -> bool:
        return run_launch_actions.handle_debug_project_action(self)

    def handle_run_with_configuration_action(self) -> bool:
        return run_launch_actions.handle_run_with_configuration_action(self)

    def handle_run_with_arguments_action(self) -> bool:
        return run_launch_actions.handle_run_with_arguments_action(self)

    def launch_ad_hoc_run_invocation(self, invocation: RunInvocation) -> bool:
        return launch_ad_hoc_run_invocation(self, invocation)

    def handle_run_active_configuration_action(self) -> bool:
        return run_launch_actions.handle_run_active_configuration_action(self)

    def handle_rerun_last_debug_target_action(self) -> None:
        run_launch_targets.handle_rerun_last_debug_target_action(self)

    def handle_tree_run_file(self, absolute_path: str) -> bool:
        return run_launch_targets.handle_tree_run_file(self, absolute_path)

    def handle_tree_run_file_with_arguments(self, absolute_path: str) -> bool:
        return run_launch_targets.handle_tree_run_file_with_arguments(self, absolute_path)

    def install_active_run_config_indicator(self) -> None:
        self._run_configuration.install_active_run_config_indicator()

    def refresh_active_run_config_indicator(self) -> None:
        self._run_configuration.refresh_active_run_config_indicator()

    def delete_transient_entry_file(self, path: str) -> None:
        self._active_file_launch.delete_transient_entry_file(path)

    def _start_active_file_session(self, *, mode: str) -> bool:
        return self._active_file_launch.start_active_file_session(
            mode=mode,
            start_session=self.start_session,
            record_debug_target=lambda file_path: self.record_debug_target(
                ActiveFileTarget(file_path=file_path)
            ),
        )
