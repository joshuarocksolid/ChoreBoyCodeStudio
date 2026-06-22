"""Host ports for run/debug launch orchestration."""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from PySide2.QtWidgets import QMessageBox, QStatusBar, QTabWidget, QWidget

from app.core.models import LoadedProject, RuntimeIssue
from app.debug.debug_models import DebugExceptionPolicy
from app.editors.editor_manager import EditorManager
from app.persistence.settings_service import SettingsService
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.run_config_controller import RunConfigController
from app.shell.run_debug_presenter import RunDebugPresenterPort
from app.shell.shell_composition_context import MainWindowCompositionSurface
from app.shell.test_runner_workflow import TestRunnerWorkflow
from app.shell.theme_tokens import ShellThemeTokens


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

    def editor_manager(self) -> EditorManager:
        ...

    def debug_control_workflow(self) -> DebugControlWorkflow:
        ...

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        ...

    def run_config_controller(self) -> RunConfigController:
        ...

    def run_debug_presenter(self) -> RunDebugPresenterPort:
        ...

    def settings_service(self) -> SettingsService:
        ...

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        ...

    def show_run_preflight_result(
        self,
        title: str,
        summary: str,
        issues: list[RuntimeIssue],
    ) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def editor_tab_factory(self) -> EditorTabFactory:
        ...

    def editor_tabs_widget(self) -> QTabWidget | None:
        ...

    def tab_index_for_path(self, file_path: str) -> int:
        ...

    def test_runner_workflow(self) -> TestRunnerWorkflow:
        ...

    def active_transient_entry_file_path(self) -> str | None:
        ...

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        ...

    def status_bar(self) -> QStatusBar:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...

    def show_information(self, title: str, message: str) -> None:
        ...

    def logger(self) -> logging.Logger:
        ...


class MainWindowRunLaunchHost:
    """Host ports for ``RunLaunchWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        self._window = cast(Any, window)

    def dialog_parent(self) -> QWidget:
        return self._window

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._window._loaded_project = project

    def active_named_run_config_name(self) -> str | None:
        return self._window._active_named_run_config_name

    def set_active_named_run_config_name(self, name: str | None) -> None:
        self._window._active_named_run_config_name = name

    def editor_manager(self) -> EditorManager:
        return self._window._editor_manager

    def debug_control_workflow(self) -> DebugControlWorkflow:
        return self._window._debug_control_workflow

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        return self._window._debug_exception_policy

    def run_config_controller(self) -> RunConfigController:
        return self._window._run_config_controller

    def run_debug_presenter(self) -> RunDebugPresenterPort:
        return self._window._run_debug_presenter

    def settings_service(self) -> SettingsService:
        return self._window._settings_service

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        return self._window._shell_theme_workflow.resolve_theme_tokens()

    def show_run_preflight_result(self, title: str, summary: str, issues: list[RuntimeIssue]) -> None:
        self._window._run_event_workflow.show_run_preflight_result(title, summary, issues)

    def refresh_run_action_states(self) -> None:
        self._window._run_event_workflow.refresh_run_action_states()

    def editor_tab_factory(self) -> EditorTabFactory:
        return self._window._editor_tab_factory

    def editor_tabs_widget(self) -> QTabWidget | None:
        return self._window._editor_tabs_widget

    def tab_index_for_path(self, file_path: str) -> int:
        return self._window._editor_tab_workflow.tab_index_for_path(file_path)

    def test_runner_workflow(self) -> TestRunnerWorkflow:
        return self._window._test_runner_workflow

    def active_transient_entry_file_path(self) -> str | None:
        return self._window._active_transient_entry_file_path

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        self._window._active_transient_entry_file_path = path

    def status_bar(self) -> QStatusBar:
        return self._window.statusBar()

    def show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self._window, title, message)

    def show_information(self, title: str, message: str) -> None:
        QMessageBox.information(self._window, title, message)

    def logger(self) -> logging.Logger:
        return self._window._logger
