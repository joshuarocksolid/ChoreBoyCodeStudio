"""Status bar scaffolding for the T05 shell.

This module intentionally stays thin:
- startup status presentation only
- no project-service wiring
- no run/runner state wiring
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.core.models import CapabilityProbeReport

if TYPE_CHECKING:
    from PySide2.QtWidgets import QLabel, QMainWindow, QStatusBar


@dataclass(frozen=True)
class StartupStatusView:
    """UI-friendly startup state derived from capability probe output."""

    severity: str
    text: str
    details: str


@dataclass(frozen=True)
class EditorStatusView:
    """UI-friendly editor telemetry state for the status bar."""

    text: str


def map_startup_report_to_status(report: Optional[CapabilityProbeReport]) -> StartupStatusView:
    """Map capability probe output into deterministic status bar copy."""
    if report is None:
        return StartupStatusView(
            severity="unknown",
            text="Startup: Capability data unavailable",
            details="Startup capability data was not provided to the editor shell.",
        )

    if report.all_available:
        return StartupStatusView(
            severity="ok",
            text=f"Startup: Runtime ready ({report.available_count}/{report.total_count} checks)",
            details="All startup capability checks passed.",
        )

    failed_checks = ", ".join(report.failed_check_ids)
    return StartupStatusView(
        severity="warning",
        text=f"Startup: Runtime issues ({report.available_count}/{report.total_count} checks)",
        details=f"Failed checks: {failed_checks}",
    )


def map_editor_status_view(file_name: str | None, line: int | None, column: int | None, is_dirty: bool) -> EditorStatusView:
    """Format editor telemetry into deterministic status copy."""
    if not file_name:
        return EditorStatusView(text="Editor: no file")

    safe_line = max(1, line or 1)
    safe_column = max(1, column or 1)
    dirty_text = "modified" if is_dirty else "saved"
    return EditorStatusView(text=f"Editor: {file_name} | Ln {safe_line}, Col {safe_column} | {dirty_text}")


class ShellStatusBarController:
    """Small controller for shell status bar labels."""

    def __init__(
        self,
        status_bar: "QStatusBar",
        startup_label: "QLabel",
        project_label: "QLabel",
        editor_label: "QLabel",
    ) -> None:
        self._status_bar = status_bar
        self._startup_label = startup_label
        self._project_label = project_label
        self._editor_label = editor_label

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Update startup status label from the latest probe output."""
        startup_status = map_startup_report_to_status(report)
        self._startup_label.setText(startup_status.text)
        self._startup_label.setToolTip(startup_status.details)
        self._startup_label.setProperty("startupSeverity", startup_status.severity)

    def set_project_state_text(self, text: str) -> None:
        """Update lightweight project-status copy."""
        self._project_label.setText(text)

    def set_editor_status(self, file_name: str | None, line: int | None, column: int | None, is_dirty: bool) -> None:
        """Update current editor telemetry in the status bar."""
        view = map_editor_status_view(file_name=file_name, line=line, column=column, is_dirty=is_dirty)
        self._editor_label.setText(view.text)

    @property
    def status_bar(self) -> "QStatusBar":
        return self._status_bar


def create_shell_status_bar(
    main_window: "QMainWindow",
    startup_report: Optional[CapabilityProbeReport] = None,
) -> ShellStatusBarController:
    """Create and attach a status bar shell to the given window."""
    from PySide2.QtWidgets import QLabel, QStatusBar

    status_bar = QStatusBar(main_window)
    status_bar.setObjectName("shell.statusBar")

    startup_label = QLabel(status_bar)
    startup_label.setObjectName("shell.startupStatusLabel")

    project_label = QLabel("Project: none loaded", status_bar)
    project_label.setObjectName("shell.projectStatusLabel")

    editor_label = QLabel("Editor: no file", status_bar)
    editor_label.setObjectName("shell.editorStatusLabel")

    status_bar.addWidget(startup_label, 1)
    status_bar.addPermanentWidget(project_label, 0)
    status_bar.addPermanentWidget(editor_label, 0)
    main_window.setStatusBar(status_bar)

    controller = ShellStatusBarController(status_bar, startup_label, project_label, editor_label)
    controller.set_startup_report(startup_report)
    return controller
