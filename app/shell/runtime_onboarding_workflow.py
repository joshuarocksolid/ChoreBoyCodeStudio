"""Runtime onboarding, welcome screen, and Runtime Center shell workflow."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Protocol

from PySide2.QtWidgets import QDialog, QStackedWidget, QVBoxLayout, QWidget

from app.bootstrap.startup_facade import StartupCapabilityFacade
from app.core import constants
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssueReport
from app.persistence.settings_service import SettingsService
from app.project.recent_projects import load_recent_projects
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.status_bar import ShellStatusBarController, map_startup_report_to_status
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.welcome_widget import WelcomeWidget
from app.support.diagnostics import ProjectHealthReport
from app.support.runtime_explainer import (
    HELP_TOPIC_GETTING_STARTED,
    HELP_TOPIC_HEADLESS_NOTES,
    build_project_health_issue_report,
    build_startup_issue_report,
    merge_runtime_issue_reports,
)


class RuntimeOnboardingHost(Protocol):
    """Narrow host ports for :class:`RuntimeOnboardingWorkflow`."""

    def dialog_parent(self) -> QWidget:
        ...

    @property
    def startup_report(self) -> CapabilityProbeReport | None:
        ...

    def set_startup_report_value(self, report: CapabilityProbeReport | None) -> None:
        ...

    @property
    def latest_health_report(self) -> ProjectHealthReport | None:
        ...

    @property
    def latest_import_issue_report(self) -> RuntimeIssueReport:
        ...

    @property
    def latest_run_issue_report(self) -> RuntimeIssueReport:
        ...

    @property
    def latest_package_issue_report(self) -> RuntimeIssueReport:
        ...

    @property
    def latest_runtime_issue_report(self) -> RuntimeIssueReport:
        ...

    def set_latest_runtime_issue_report(self, report: RuntimeIssueReport) -> None:
        ...

    def state_root(self) -> str | None:
        ...

    def settings_service(self) -> SettingsService:
        ...

    def logger(self) -> logging.Logger:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    @property
    def welcome_widget(self) -> WelcomeWidget | None:
        ...

    @property
    def center_stack(self) -> QStackedWidget | None:
        ...

    def startup_capability_facade(self) -> StartupCapabilityFacade:
        ...

    def background_tasks(self) -> GeneralTaskScheduler:
        ...

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        ...

    def status_controller(self) -> ShellStatusBarController | None:
        ...

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        ...

    def open_runtime_help_topic(self, topic_id: str) -> None:
        ...

    def handle_new_project_action(self) -> None:
        ...

    def handle_open_project_action(self) -> None:
        ...

    def open_project_by_path(self, project_path: str) -> bool:
        ...

    def handle_getting_started_action(self) -> None:
        ...

    def handle_project_health_check_action(self) -> None:
        ...

    def handle_load_example_project_action(self) -> None:
        ...

    def show_headless_notes(self) -> None:
        ...


class MainWindowRuntimeOnboardingHost:
    """Adapts :class:`MainWindow` to :class:`RuntimeOnboardingHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> QWidget:
        return self._window

    @property
    def startup_report(self) -> CapabilityProbeReport | None:
        return self._window._startup_report

    def set_startup_report_value(self, report: CapabilityProbeReport | None) -> None:
        self._window._startup_report = report

    @property
    def latest_health_report(self) -> ProjectHealthReport | None:
        return self._window._latest_health_report

    @property
    def latest_import_issue_report(self) -> RuntimeIssueReport:
        return self._window._latest_import_issue_report

    @property
    def latest_run_issue_report(self) -> RuntimeIssueReport:
        return self._window._latest_run_issue_report

    @property
    def latest_package_issue_report(self) -> RuntimeIssueReport:
        return self._window._latest_package_issue_report

    @property
    def latest_runtime_issue_report(self) -> RuntimeIssueReport:
        return self._window._latest_runtime_issue_report

    def set_latest_runtime_issue_report(self, report: RuntimeIssueReport) -> None:
        self._window._latest_runtime_issue_report = report

    def state_root(self) -> str | None:
        return self._window._state_root

    def settings_service(self) -> SettingsService:
        return self._window._settings_service

    def logger(self) -> logging.Logger:
        return self._window._logger

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    @property
    def welcome_widget(self) -> WelcomeWidget | None:
        return self._window._welcome_widget

    @property
    def center_stack(self) -> QStackedWidget | None:
        return self._window._center_stack

    def startup_capability_facade(self) -> StartupCapabilityFacade:
        return self._window._startup_capability_facade

    def background_tasks(self) -> GeneralTaskScheduler:
        return self._window._background_tasks

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        self._window._dispatch_to_main_thread(callback)

    def status_controller(self) -> ShellStatusBarController | None:
        return self._window._status_controller

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        return self._window._shell_theme_workflow.resolve_theme_tokens()

    def open_runtime_help_topic(self, topic_id: str) -> None:
        if topic_id == HELP_TOPIC_HEADLESS_NOTES:
            self._window._help_controller.show_headless_notes(parent=self._window)
            return
        if topic_id == "packaging_backup":
            self._window._help_controller.show_packaging_backup(parent=self._window)
            return
        if topic_id == HELP_TOPIC_GETTING_STARTED:
            self._window._help_controller.show_getting_started(parent=self._window)
            return
        self._window._help_controller.show_getting_started(parent=self._window)

    def handle_new_project_action(self) -> None:
        self._window._file_project_commands_workflow.handle_new_project_action()

    def handle_open_project_action(self) -> None:
        self._window._file_project_commands_workflow.handle_open_project_action()

    def open_project_by_path(self, project_path: str) -> bool:
        return self._window._file_project_commands_workflow.open_project_by_path(project_path)

    def handle_getting_started_action(self) -> None:
        self._window._handle_getting_started_action()

    def handle_project_health_check_action(self) -> None:
        self._window._runtime_support_workflow.handle_project_health_check_action()

    def handle_load_example_project_action(self) -> None:
        self._window._file_project_commands_workflow.handle_load_example_project_action()

    def show_headless_notes(self) -> None:
        self._window._help_controller.show_headless_notes(parent=self._window)


class RuntimeOnboardingWorkflow:
    """Owns startup report refresh, Runtime Center, welcome screen, and onboarding."""

    def __init__(self, host: RuntimeOnboardingHost) -> None:
        self._host = host
        self._runtime_onboarding_dismissed, self._runtime_onboarding_completed = self._load_runtime_onboarding_state()

    def set_startup_report(self, report: CapabilityProbeReport | None) -> None:
        """Apply bootstrap startup report updates to shell state and welcome UI."""
        self._host.set_startup_report_value(report)
        self._host.set_latest_runtime_issue_report(self.build_runtime_issue_report())
        self.refresh_welcome_project_list()
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        status_controller.set_startup_report(report)

    def refresh_startup_capability_report_async(self) -> None:
        def task(cancel_event):  # type: ignore[no-untyped-def]
            report = self._host.startup_capability_facade().refresh_report()
            if cancel_event.is_set():
                return None
            return report

        def on_success(report: object) -> None:
            if not isinstance(report, CapabilityProbeReport):
                return
            self.set_startup_report(report)

        def on_error(exc: Exception) -> None:
            self._host.logger().warning("Deferred startup capability probe failed: %s", exc)

        self._host.background_tasks().run(
            key="startup_capability_refresh",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def handle_startup_report_refresh(self, report: CapabilityProbeReport) -> None:
        self._host.dispatch_to_main_thread(lambda: self.set_startup_report(report))

    def build_runtime_issue_report(self) -> RuntimeIssueReport:
        reports: list[RuntimeIssueReport] = []
        startup_report = self._host.startup_report
        startup_issues = (
            build_startup_issue_report(startup_report)
            if startup_report is not None
            else RuntimeIssueReport(workflow="startup", issues=[])
        )
        reports.append(startup_issues)
        latest_health_report = self._host.latest_health_report
        if latest_health_report is not None:
            reports.append(build_project_health_issue_report(latest_health_report))
        latest_import_issue_report = self._host.latest_import_issue_report
        if latest_import_issue_report.issues:
            reports.append(latest_import_issue_report)
        latest_run_issue_report = self._host.latest_run_issue_report
        if latest_run_issue_report.issues:
            reports.append(latest_run_issue_report)
        latest_package_issue_report = self._host.latest_package_issue_report
        if latest_package_issue_report.issues:
            reports.append(latest_package_issue_report)
        return merge_runtime_issue_reports(*reports, workflow="runtime_center")

    def refresh_latest_runtime_issue_report(self) -> None:
        self._host.set_latest_runtime_issue_report(self.build_runtime_issue_report())

    def open_runtime_center_dialog(
        self,
        *,
        title: str = "Runtime Center",
        report: RuntimeIssueReport | None = None,
    ) -> None:
        dialog = RuntimeCenterDialog(
            title=title,
            report=report or self._host.latest_runtime_issue_report,
            tokens=self._host.resolve_theme_tokens(),
            open_help_topic=self._host.open_runtime_help_topic,
            parent=self._host.dialog_parent(),
        )
        dialog.exec_()

    def handle_runtime_center_action(self) -> None:
        self.refresh_latest_runtime_issue_report()
        self.open_runtime_center_dialog()

    def refresh_welcome_widget_state(
        self,
        widget: WelcomeWidget,
        *,
        force_show_onboarding: bool = False,
    ) -> None:
        try:
            recent_paths = load_recent_projects(state_root=self._host.state_root())
        except Exception as exc:
            self._host.logger().debug("Recent projects unavailable for welcome widget: %s", exc)
            recent_paths = []
        widget.set_recent_projects(recent_paths)
        startup_status = map_startup_report_to_status(self._host.startup_report)
        widget.set_runtime_summary(startup_status.text, startup_status.details)
        widget.set_project_health_available(self._host.loaded_project() is not None)
        widget.set_onboarding_visible(force_show_onboarding)

    def connect_welcome_widget_actions(
        self,
        widget: WelcomeWidget,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        widget.new_project_requested.connect(
            lambda: self._invoke_welcome_action(self._host.handle_new_project_action, close_after_action)
        )
        widget.open_project_requested.connect(
            lambda: self._invoke_welcome_action(self._host.handle_open_project_action, close_after_action)
        )
        widget.project_selected.connect(
            lambda project_path: self._handle_welcome_project_selected(project_path, close_after_action)
        )
        widget.runtime_center_requested.connect(
            lambda: self._invoke_welcome_action(self.handle_runtime_center_action, close_after_action)
        )
        widget.getting_started_requested.connect(
            lambda: self._invoke_welcome_action(self._host.handle_getting_started_action, close_after_action)
        )
        widget.project_health_requested.connect(
            lambda: self._invoke_welcome_action(
                self._host.handle_project_health_check_action,
                close_after_action,
            )
        )
        widget.example_project_requested.connect(
            lambda: self._invoke_welcome_action(self._host.handle_load_example_project_action, close_after_action)
        )
        widget.headless_notes_requested.connect(
            lambda: self._invoke_welcome_action(self._host.show_headless_notes, close_after_action)
        )
        widget.dismiss_onboarding_requested.connect(
            lambda: self._handle_runtime_onboarding_dismiss_action(close_after_action=close_after_action)
        )
        widget.complete_onboarding_requested.connect(
            lambda: self._handle_runtime_onboarding_complete_action(close_after_action=close_after_action)
        )

    def refresh_welcome_project_list(self) -> None:
        welcome_widget = self._host.welcome_widget
        if welcome_widget is None:
            return
        self.refresh_welcome_widget_state(welcome_widget)

    def show_welcome_screen(self) -> None:
        center_stack = self._host.center_stack
        if center_stack is not None:
            self.refresh_welcome_project_list()
            center_stack.setCurrentIndex(0)

    def show_editor_screen(self) -> None:
        center_stack = self._host.center_stack
        if center_stack is not None:
            center_stack.setCurrentIndex(1)

    def handle_runtime_onboarding_action(self) -> None:
        parent = self._host.dialog_parent()
        dialog = QDialog(parent)
        dialog.setObjectName("shell.runtimeOnboardingDialog")
        dialog.setWindowTitle("Runtime Onboarding")
        dialog.resize(760, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        onboarding_widget = WelcomeWidget(dialog)
        self.connect_welcome_widget_actions(onboarding_widget, close_after_action=dialog.accept)
        self.refresh_welcome_widget_state(onboarding_widget, force_show_onboarding=True)
        layout.addWidget(onboarding_widget)
        dialog.exec_()

    def _invoke_welcome_action(
        self,
        action: Callable[[], None],
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        if close_after_action is not None:
            close_after_action()
        action()

    def _handle_welcome_project_selected(
        self,
        project_path: str,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        opened = self._host.open_project_by_path(project_path)
        if opened and close_after_action is not None:
            close_after_action()

    def _handle_runtime_onboarding_dismiss_action(
        self,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        self._persist_runtime_onboarding_state(dismissed=True, completed=False)
        if close_after_action is not None:
            close_after_action()

    def _handle_runtime_onboarding_complete_action(
        self,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        self._persist_runtime_onboarding_state(dismissed=False, completed=True)
        if close_after_action is not None:
            close_after_action()

    def _load_runtime_onboarding_state(self) -> tuple[bool, bool]:
        try:
            settings_payload = self._host.settings_service().load_global()
        except Exception as exc:
            self._host.logger().debug("Runtime onboarding state unavailable; using defaults: %s", exc)
            return False, False
        onboarding_payload = settings_payload.get(constants.UI_ONBOARDING_SETTINGS_KEY)
        if not isinstance(onboarding_payload, Mapping):
            return False, False
        return (
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_DISMISSED_KEY, False)),
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_COMPLETED_KEY, False)),
        )

    def _persist_runtime_onboarding_state(self, *, dismissed: bool | None = None, completed: bool | None = None) -> None:
        if dismissed is not None:
            self._runtime_onboarding_dismissed = dismissed
        if completed is not None:
            self._runtime_onboarding_completed = completed
        try:
            self._host.settings_service().update_global(
                lambda settings: self._merge_runtime_onboarding_settings(
                    settings,
                    dismissed=self._runtime_onboarding_dismissed,
                    completed=self._runtime_onboarding_completed,
                )
            )
        except Exception as exc:
            self._host.logger().warning("Failed to persist runtime onboarding state: %s", exc)
        self.refresh_welcome_project_list()

    @staticmethod
    def _merge_runtime_onboarding_settings(
        settings: Mapping[str, Any],
        *,
        dismissed: bool,
        completed: bool,
    ) -> dict[str, Any]:
        updated = dict(settings)
        existing = settings.get(constants.UI_ONBOARDING_SETTINGS_KEY)
        onboarding_payload = dict(existing) if isinstance(existing, Mapping) else {}
        onboarding_payload[constants.UI_ONBOARDING_RUNTIME_GUIDE_DISMISSED_KEY] = dismissed
        onboarding_payload[constants.UI_ONBOARDING_RUNTIME_GUIDE_COMPLETED_KEY] = completed
        updated[constants.UI_ONBOARDING_SETTINGS_KEY] = onboarding_payload
        return updated
