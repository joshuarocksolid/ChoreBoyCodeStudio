"""Run configuration UX: dialogs, persistence, and status-bar indicator."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMenu, QStatusBar, QToolButton, QWidget

from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import LoadedProject
from app.project.project_manifest import set_project_default_argv
from app.project.run_configs import RunConfiguration
from app.shell.run_config_controller import RunConfigController
from app.shell.run_configurations_dialog import (
    RunConfigurationsDialog,
    RunConfigurationsInitial,
    RunConfigurationsResult,
)
from app.shell.theme_tokens import ShellThemeTokens


def proposed_new_config_name(existing_configs: list[RunConfiguration]) -> str:
    """Return a unique default name for a freshly created run configuration."""

    base = "New Configuration"
    existing_names = {config.name for config in existing_configs}
    if base not in existing_names:
        return base
    index = 2
    while f"{base} {index}" in existing_names:
        index += 1
    return f"{base} {index}"


class RunConfigurationHost(Protocol):
    def dialog_parent(self) -> QWidget:
        ...

    def status_bar(self) -> QStatusBar:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def set_loaded_project(self, project: LoadedProject) -> None:
        ...

    def active_named_run_config_name(self) -> str | None:
        ...

    def set_active_named_run_config_name(self, name: str | None) -> None:
        ...

    def run_config_controller(self) -> RunConfigController:
        ...

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...

    def handle_run_with_arguments_action(self) -> bool:
        ...

    def handle_run_with_configuration_action(self) -> bool:
        ...


class RunConfigurationWorkflow:
    """Run-configuration dialogs and status-bar active-config indicator."""

    def __init__(self, host: RunConfigurationHost) -> None:
        self._host = host
        self._active_run_config_button: QToolButton | None = None

    def resolve_active_named_run_config(self) -> RunConfiguration | None:
        loaded_project = self._host.loaded_project()
        active_name = self._host.active_named_run_config_name()
        if loaded_project is None or not active_name:
            return None
        configs = self._host.run_config_controller().load_configs(loaded_project)
        for config in configs:
            if config.name == active_name:
                return config
        self._host.set_active_named_run_config_name(None)
        self.refresh_active_run_config_indicator()
        return None

    def persist_run_configurations_result(self, result: RunConfigurationsResult) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return False
        try:
            self._host.run_config_controller().persist_run_configs(
                loaded_project=loaded_project,
                run_configs=result.configurations,
            )
        except AppValidationError as exc:
            self._host.show_warning("Run Configurations", str(exc))
            return False
        try:
            updated_metadata = set_project_default_argv(
                loaded_project.manifest_path,
                default_argv=list(result.default_argv),
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            self._host.show_warning("Run Configurations", str(exc))
            return False
        self._host.set_loaded_project(
            replace(
                loaded_project,
                metadata=updated_metadata,
                manifest_materialized=True,
            )
        )
        selected_name = result.selected_config_name
        existing_names = {config.name for config in result.configurations}
        if selected_name and selected_name in existing_names:
            self._host.set_active_named_run_config_name(selected_name)
        elif (
            self._host.active_named_run_config_name() is not None
            and self._host.active_named_run_config_name() not in existing_names
        ):
            self._host.set_active_named_run_config_name(None)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()
        return True

    def install_active_run_config_indicator(self) -> None:
        if self._active_run_config_button is not None:
            return
        status_bar = self._host.status_bar()
        button = QToolButton(status_bar)
        button.setObjectName("shell.statusBar.activeRunConfig")
        button.setText("Default")
        button.setToolTip(
            "Active run target for F5 / Run Project. Click to switch configurations or edit them."
        )
        button.setPopupMode(QToolButton.InstantPopup)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
        button.setMenu(QMenu(button))
        button.menu().aboutToShow.connect(self._populate_active_run_config_menu)
        status_bar.addPermanentWidget(button)
        self._active_run_config_button = button
        self.refresh_active_run_config_indicator()

    def refresh_active_run_config_indicator(self) -> None:
        button = self._active_run_config_button
        if button is None:
            return
        active_name = self._host.active_named_run_config_name()
        button.setText(active_name if active_name else "Default")
        button.setEnabled(True)

    def _populate_active_run_config_menu(self) -> None:
        button = self._active_run_config_button
        if button is None:
            return
        menu = button.menu()
        if menu is None:
            return
        menu.clear()
        loaded_project = self._host.loaded_project()

        default_action = menu.addAction("Default (no named configuration)")
        default_action.setCheckable(True)
        default_action.setChecked(self._host.active_named_run_config_name() is None)
        default_action.triggered.connect(self._set_active_run_config_to_default)

        if loaded_project is not None:
            configs = self._host.run_config_controller().load_configs(loaded_project)
        else:
            configs = []
        if configs:
            menu.addSeparator()
            for config in configs:
                action = menu.addAction(config.name)
                action.setCheckable(True)
                action.setChecked(config.name == self._host.active_named_run_config_name())
                action.triggered.connect(
                    lambda _checked=False, name=config.name: self._set_active_run_config_by_name(name)
                )
        menu.addSeparator()
        run_with_args_action = menu.addAction("Run With Arguments...")
        run_with_args_action.triggered.connect(self._host.handle_run_with_arguments_action)
        edit_action = menu.addAction("Edit Configurations...")
        edit_action.setEnabled(loaded_project is not None)
        edit_action.triggered.connect(self._host.handle_run_with_configuration_action)

    def _set_active_run_config_to_default(self) -> None:
        if self._host.active_named_run_config_name() is None:
            return
        self._host.set_active_named_run_config_name(None)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()

    def _set_active_run_config_by_name(self, name: str) -> None:
        normalized = (name or "").strip()
        if not normalized:
            return
        if normalized == self._host.active_named_run_config_name():
            return
        self._host.set_active_named_run_config_name(normalized)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()
