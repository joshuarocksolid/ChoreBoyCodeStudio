"""Status bar scaffolding for the T05 shell.

This module intentionally stays thin:
- startup status presentation only
- lightweight project/editor/diagnostics wiring
- lightweight run-state wiring
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol, cast

from app.core.models import CapabilityProbeReport
from app.shell.python_tooling_status_copy import format_python_tooling_status_copy
from app.support.runtime_explainer import build_startup_issue_report

if TYPE_CHECKING:
    from PySide2.QtWidgets import QLabel, QMainWindow, QStatusBar


class _EmittableSignal(Protocol):
    def emit(self) -> None:
        ...


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


@dataclass(frozen=True)
class RunStatusView:
    """UI-friendly run lifecycle state for the status bar."""

    severity: str
    text: str
    details: str


@dataclass(frozen=True)
class PythonToolingStatusView:
    """UI-friendly Python tooling readiness state for the status bar."""

    severity: str
    text: str
    details: str


@dataclass(frozen=True)
class IndentStatusView:
    """UI-friendly indentation state for the status bar.

    `text` is empty when no editor is active. `details` populates the tooltip
    so the user can tell *why* a particular indent setting is active (their
    own settings, an `.editorconfig`, or auto-detection from file content).
    """

    text: str
    details: str


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

    issue_report = build_startup_issue_report(report)
    issue_titles = "; ".join(issue.title for issue in issue_report.issues)
    detail_text = f"{issue_report.total_count} issue(s): {issue_titles}" if issue_titles else "Startup capability checks reported issues."
    return StartupStatusView(
        severity="warning",
        text=f"Startup: Runtime issues ({report.available_count}/{report.total_count} checks)",
        details=detail_text,
    )


def map_editor_status_view(file_name: str | None, line: int | None, column: int | None, is_dirty: bool) -> EditorStatusView:
    """Format editor telemetry into deterministic status copy."""
    if not file_name:
        return EditorStatusView(text="Editor: no file")

    safe_line = max(1, line or 1)
    safe_column = max(1, column or 1)
    dirty_text = "modified" if is_dirty else "saved"
    return EditorStatusView(text=f"Editor: {file_name} | Ln {safe_line}, Col {safe_column} | {dirty_text}")


def format_diagnostics_counts(errors: int, warnings: int) -> str:
    """Format diagnostic counts for status bar display."""
    parts: list[str] = []
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
    if not parts:
        return ""
    return ", ".join(parts)


def map_run_status_view(status: str, *, return_code: int | None = None) -> RunStatusView:
    """Map run lifecycle status into deterministic status bar copy."""
    if status == "running":
        return RunStatusView(
            severity="running",
            text="Run: running",
            details="A run/debug session is currently active.",
        )
    if status == "stopping":
        return RunStatusView(
            severity="stopping",
            text="Run: stopping",
            details="Stop requested. Waiting for runner process to exit.",
        )
    if status == "success":
        code = 0 if return_code is None else int(return_code)
        return RunStatusView(
            severity="ok",
            text=f"Run: success (code={code})",
            details="Latest run completed successfully.",
        )
    if status == "terminated":
        detail = "Latest run was terminated by the user."
        if return_code is not None:
            detail = f"{detail} Exit code: {return_code}."
        return RunStatusView(
            severity="warning",
            text="Run: terminated",
            details=detail,
        )
    if status == "failed":
        code = "?" if return_code is None else str(int(return_code))
        return RunStatusView(
            severity="error",
            text=f"Run: failed (code={code})",
            details="Latest run exited with an error.",
        )
    return RunStatusView(
        severity="idle",
        text="Run: idle",
        details="No active run/debug session.",
    )


def map_indent_status_view(
    *,
    style: Optional[str],
    size: Optional[int],
    source: Optional[str],
) -> IndentStatusView:
    """Format active editor indentation into deterministic status copy."""
    if style is None or size is None or source is None:
        return IndentStatusView(text="", details="")

    label = "Tabs" if style == "tabs" else "Spaces"
    suffix = " (auto)" if source == "auto" else ""
    text = f"{label}: {int(size)}{suffix}"

    if source == "auto":
        details = "Auto-detected from file content. Adjust 'detect indentation from file' in editor settings to override."
    elif source == "editorconfig":
        details = "Indent settings come from the project's .editorconfig file."
    else:
        details = "Indent settings come from your editor settings."
    return IndentStatusView(text=text, details=details)


def map_python_tooling_status_view(
    *,
    runtime_available: bool,
    config_state: str,
    config_path: str | None = None,
    config_error: str | None = None,
) -> PythonToolingStatusView:
    """Map Python tooling/runtime metadata into concise status-bar copy."""
    copy = format_python_tooling_status_copy(
        runtime_available=runtime_available,
        config_state=config_state,
        config_path=config_path,
        config_error=config_error,
    )
    return PythonToolingStatusView(severity=copy.severity, text=copy.text, details=copy.details)


class ShellStatusBarController:
    """Small controller for shell status bar labels."""

    def __init__(
        self,
        status_bar: "QStatusBar",
        startup_label: "QLabel",
        python_tooling_label: "QLabel",
        run_label: "QLabel",
        project_label: "QLabel",
        editor_label: "QLabel",
        diagnostics_label: "QLabel",
        indent_label: "QLabel",
    ) -> None:
        self._status_bar = status_bar
        self._startup_label = startup_label
        self._python_tooling_label = python_tooling_label
        self._run_label = run_label
        self._project_label = project_label
        self._editor_label = editor_label
        self._diagnostics_label = diagnostics_label
        self._indent_label = indent_label

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Update startup status label from the latest probe output."""
        startup_status = map_startup_report_to_status(report)
        self._startup_label.setText(startup_status.text)
        tooltip = startup_status.details
        if bool(self._startup_label.property("startupInteractive")):
            tooltip = f"{tooltip}\n\nClick to open Runtime Center."
        self._startup_label.setToolTip(tooltip)
        self._startup_label.setProperty("startupSeverity", startup_status.severity)  # type: ignore[arg-type]

    def set_project_state_text(self, text: str) -> None:
        """Update lightweight project-status copy."""
        self._project_label.setText(text)

    def set_python_tooling_status(
        self,
        *,
        runtime_available: bool,
        config_state: str,
        config_path: str | None = None,
        config_error: str | None = None,
    ) -> None:
        """Update Python tooling readiness copy."""
        view = map_python_tooling_status_view(
            runtime_available=runtime_available,
            config_state=config_state,
            config_path=config_path,
            config_error=config_error,
        )
        self._python_tooling_label.setText(view.text)
        self._python_tooling_label.setToolTip(view.details)
        self._python_tooling_label.setProperty("pythonToolingSeverity", view.severity)  # type: ignore[arg-type]

    def set_editor_status(self, file_name: str | None, line: int | None, column: int | None, is_dirty: bool) -> None:
        """Update current editor telemetry in the status bar."""
        view = map_editor_status_view(file_name=file_name, line=line, column=column, is_dirty=is_dirty)
        self._editor_label.setText(view.text)

    def set_diagnostics_counts(self, errors: int, warnings: int) -> None:
        """Update diagnostic counts in the status bar."""
        text = format_diagnostics_counts(errors, warnings)
        self._diagnostics_label.setText(text)
        self._diagnostics_label.setVisible(bool(text))

    def set_indent_status(
        self,
        *,
        style: Optional[str],
        size: Optional[int],
        source: Optional[str],
    ) -> None:
        """Update editor indentation copy in the status bar."""
        view = map_indent_status_view(style=style, size=size, source=source)
        self._indent_label.setText(view.text)
        self._indent_label.setToolTip(view.details)
        self._indent_label.setVisible(bool(view.text))

    def set_run_status(self, status: str, *, return_code: int | None = None) -> None:
        """Update run/debug lifecycle status in the status bar."""
        run_view = map_run_status_view(status, return_code=return_code)
        self._run_label.setText(run_view.text)
        self._run_label.setToolTip(run_view.details)
        self._run_label.setProperty("runSeverity", run_view.severity)  # type: ignore[arg-type]

    @property
    def status_bar(self) -> "QStatusBar":
        return self._status_bar


def create_shell_status_bar(
    main_window: "QMainWindow",
    startup_report: Optional[CapabilityProbeReport] = None,
    on_startup_activated: object | None = None,
) -> ShellStatusBarController:
    """Create and attach a status bar shell to the given window."""
    from PySide2 import QtCore, QtGui
    from PySide2.QtWidgets import QLabel, QStatusBar

    class _ClickableLabel(QLabel):
        clicked = QtCore.Signal()

        def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[name-defined]
            if event.button() == QtCore.Qt.LeftButton:
                cast(_EmittableSignal, self.clicked).emit()
            super().mousePressEvent(event)

    status_bar = QStatusBar(main_window)
    status_bar.setObjectName("shell.statusBar")

    startup_label = _ClickableLabel(status_bar)
    startup_label.setObjectName("shell.startupStatusLabel")
    startup_label.setProperty("startupInteractive", bool(on_startup_activated))  # type: ignore[arg-type]
    startup_label.setCursor(QtCore.Qt.PointingHandCursor if on_startup_activated else QtCore.Qt.ArrowCursor)
    if on_startup_activated:
        startup_label.clicked.connect(on_startup_activated)  # type: ignore[arg-type]

    diagnostics_label = QLabel("", status_bar)
    diagnostics_label.setObjectName("shell.diagnosticsStatusLabel")
    diagnostics_label.setVisible(False)

    python_tooling_label = QLabel("Python: tools unknown", status_bar)
    python_tooling_label.setObjectName("shell.pythonToolingStatusLabel")

    project_label = QLabel("Project: none loaded", status_bar)
    project_label.setObjectName("shell.projectStatusLabel")

    editor_label = QLabel("Editor: no file", status_bar)
    editor_label.setObjectName("shell.editorStatusLabel")

    indent_label = QLabel("", status_bar)
    indent_label.setObjectName("shell.indentStatusLabel")
    indent_label.setVisible(False)

    run_label = QLabel("Run: idle", status_bar)
    run_label.setObjectName("shell.runStatusLabel")

    status_bar.addWidget(startup_label, 1)
    status_bar.addPermanentWidget(diagnostics_label, 0)
    status_bar.addPermanentWidget(python_tooling_label, 0)
    status_bar.addPermanentWidget(run_label, 0)
    status_bar.addPermanentWidget(project_label, 0)
    status_bar.addPermanentWidget(indent_label, 0)
    status_bar.addPermanentWidget(editor_label, 0)
    main_window.setStatusBar(status_bar)

    controller = ShellStatusBarController(
        status_bar,
        startup_label,
        python_tooling_label,
        run_label,
        project_label,
        editor_label,
        diagnostics_label,
        indent_label,
    )
    controller.set_startup_report(startup_report)
    controller.set_python_tooling_status(runtime_available=False, config_state="no_project")
    controller.set_run_status("idle")
    return controller
