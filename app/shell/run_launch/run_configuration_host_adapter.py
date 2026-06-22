"""Adapt :class:`RunLaunchWorkflow` to :class:`RunConfigurationHost`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtWidgets import QStatusBar, QWidget

from app.core.models import LoadedProject
from app.shell.run_config_controller import RunConfigController
from app.shell.theme_tokens import ShellThemeTokens

if TYPE_CHECKING:
    from app.shell.run_launch_workflow import RunLaunchWorkflow


class RunConfigurationHostAdapter:
    """Bridge ``RunLaunchWorkflow`` host ports into ``RunConfigurationWorkflow``."""

    def __init__(self, workflow: RunLaunchWorkflow) -> None:
        self._workflow = workflow

    def dialog_parent(self) -> QWidget:
        return self._workflow._host.dialog_parent()

    def status_bar(self) -> QStatusBar:
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

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        return self._workflow._host.resolve_theme_tokens()

    def refresh_run_action_states(self) -> None:
        return self._workflow._host.refresh_run_action_states()

    def show_warning(self, title: str, message: str) -> None:
        self._workflow._host.show_warning(title, message)

    def handle_run_with_arguments_action(self) -> bool:
        return self._workflow.handle_run_with_arguments_action()

    def handle_run_with_configuration_action(self) -> bool:
        return self._workflow.handle_run_with_configuration_action()
