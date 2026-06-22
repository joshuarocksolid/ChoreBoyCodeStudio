"""Composition context and timer registry for main-window shell wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from PySide2.QtCore import QTimer

from app.core.models import CapabilityProbeReport, RuntimeIssueReport
from app.persistence.autosave_store import AutosaveStore
from app.persistence.local_history_store import LocalHistoryStore
from app.support.diagnostics import ProjectHealthReport


class MainWindowCompositionSurface(Protocol):
    """Structural typing marker for MainWindow during composition wiring.

    Private attrs are bound dynamically via :func:`bind_private_attrs`; host
    adapters use :func:`typing.cast` internally when accessing those fields.
    """


def bind_private_attrs(window: MainWindowCompositionSurface, attrs: Mapping[str, Any]) -> None:
    """Assign multiple private MainWindow fields in one call."""
    for name, value in attrs.items():
        setattr(window, name, value)


@dataclass
class ShellRuntimeIssueState:
    """Runtime health/import/run/package issue fields for composition wiring."""

    latest_health_report: ProjectHealthReport | None = None
    latest_import_issue_report: RuntimeIssueReport | None = None
    latest_run_issue_report: RuntimeIssueReport | None = None
    latest_package_issue_report: RuntimeIssueReport | None = None
    latest_runtime_issue_report: RuntimeIssueReport | None = None
    latest_run_issue_ids: tuple[str, ...] = ()
    active_named_run_config_name: str | None = None

    @classmethod
    def create_initial(cls) -> ShellRuntimeIssueState:
        return cls(
            latest_import_issue_report=RuntimeIssueReport(workflow="import", issues=[]),
            latest_run_issue_report=RuntimeIssueReport(workflow="run", issues=[]),
            latest_package_issue_report=RuntimeIssueReport(workflow="package", issues=[]),
        )

    def bind_to_window(self, window: MainWindowCompositionSurface) -> None:
        bind_private_attrs(
            window,
            {
                "_latest_health_report": self.latest_health_report,
                "_latest_import_issue_report": self.latest_import_issue_report,
                "_latest_run_issue_report": self.latest_run_issue_report,
                "_latest_package_issue_report": self.latest_package_issue_report,
                "_latest_runtime_issue_report": self.latest_runtime_issue_report,
                "_latest_run_issue_ids": self.latest_run_issue_ids,
                "_active_named_run_config_name": self.active_named_run_config_name,
            },
        )

    def set_latest_health_report(
        self, window: MainWindowCompositionSurface, report: ProjectHealthReport | None
    ) -> None:
        self.latest_health_report = report
        setattr(window, "_latest_health_report", report)

    def set_latest_import_issue_report(
        self, window: MainWindowCompositionSurface, report: RuntimeIssueReport
    ) -> None:
        self.latest_import_issue_report = report
        setattr(window, "_latest_import_issue_report", report)

    def set_latest_run_issue_report(
        self, window: MainWindowCompositionSurface, report: RuntimeIssueReport
    ) -> None:
        self.latest_run_issue_report = report
        setattr(window, "_latest_run_issue_report", report)

    def set_latest_package_issue_report(
        self, window: MainWindowCompositionSurface, report: RuntimeIssueReport
    ) -> None:
        self.latest_package_issue_report = report
        setattr(window, "_latest_package_issue_report", report)

    def set_latest_runtime_issue_report(
        self, window: MainWindowCompositionSurface, report: RuntimeIssueReport
    ) -> None:
        self.latest_runtime_issue_report = report
        setattr(window, "_latest_runtime_issue_report", report)

    def clear_active_run_config(self, window: MainWindowCompositionSurface) -> None:
        self.active_named_run_config_name = None
        self.latest_run_issue_ids = ()
        setattr(window, "_active_named_run_config_name", None)
        setattr(window, "_latest_run_issue_ids", ())


@dataclass
class ShellDiagnosticsLatchState:
    """Diagnostics orchestrator latch fields stored on MainWindow."""

    pending_realtime_lint_file_path: str | None = None
    known_runtime_modules: frozenset[str] | None = None

    def bind_to_window(self, window: MainWindowCompositionSurface) -> None:
        bind_private_attrs(
            window,
            {
                "_pending_realtime_lint_file_path": self.pending_realtime_lint_file_path,
                "_known_runtime_modules": self.known_runtime_modules,
            },
        )

    def set_pending_realtime_lint_file_path(
        self, window: MainWindowCompositionSurface, file_path: str | None
    ) -> None:
        self.pending_realtime_lint_file_path = file_path
        setattr(window, "_pending_realtime_lint_file_path", file_path)

    def set_known_runtime_modules(
        self, window: MainWindowCompositionSurface, modules: frozenset[str]
    ) -> None:
        self.known_runtime_modules = modules
        setattr(window, "_known_runtime_modules", modules)


@dataclass
class ShellCompositionTimers:
    """All composition-owned QTimers for centralized lifecycle management."""

    project_tree_preview_click: QTimer
    auto_save_to_file: QTimer
    realtime_lint: QTimer
    outline_refresh: QTimer
    run_event: QTimer
    repl_event: QTimer
    external_change_poll: QTimer
    restore_project: QTimer
    auto_start_repl: QTimer
    runtime_probe: QTimer
    startup_probe_refresh: QTimer

    def stop_all(self) -> None:
        self.project_tree_preview_click.stop()
        self.auto_save_to_file.stop()
        self.realtime_lint.stop()
        self.outline_refresh.stop()
        self.run_event.stop()
        self.repl_event.stop()
        self.external_change_poll.stop()
        self.restore_project.stop()
        self.auto_start_repl.stop()
        self.runtime_probe.stop()
        self.startup_probe_refresh.stop()

    def bind_to_window(self, window: MainWindowCompositionSurface) -> None:
        bind_private_attrs(
            window,
            {
                "_composition_timers": self,
                "_project_tree_preview_click_timer": self.project_tree_preview_click,
                "_auto_save_to_file_timer": self.auto_save_to_file,
                "_realtime_lint_timer": self.realtime_lint,
                "_outline_refresh_timer": self.outline_refresh,
                "_run_event_timer": self.run_event,
                "_repl_event_timer": self.repl_event,
                "_external_change_poll_timer": self.external_change_poll,
                "_restore_project_timer": self.restore_project,
                "_auto_start_repl_timer": self.auto_start_repl,
                "_runtime_probe_timer": self.runtime_probe,
                "_startup_probe_refresh_timer": self.startup_probe_refresh,
            },
        )


@dataclass
class ShellCompositionContext:
    """Holds wired shell collaborators during phased main-window composition."""

    window: MainWindowCompositionSurface
    startup_report: Optional[CapabilityProbeReport]
    state_root: str | None
    local_history_store: LocalHistoryStore | None = None
    autosave_store: AutosaveStore | None = None
    timers: ShellCompositionTimers | None = None
    runtime_issues: ShellRuntimeIssueState | None = None
    diagnostics_latches: ShellDiagnosticsLatchState | None = None

    @property
    def w(self) -> MainWindowCompositionSurface:
        return self.window


__all__ = [
    "MainWindowCompositionSurface",
    "ShellCompositionContext",
    "ShellCompositionTimers",
    "ShellDiagnosticsLatchState",
    "ShellRuntimeIssueState",
    "bind_private_attrs",
]
