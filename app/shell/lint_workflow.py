"""Python lint execution and diagnostics result application for the shell."""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from PySide2.QtWidgets import QMessageBox

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity, find_unresolved_imports
from app.intelligence.lint_profile import LINT_SEVERITY_ERROR, LINT_SEVERITY_INFO, resolve_lint_rule_settings
from app.plugins.workflow_adapters import analyze_python_with_workflow
from app.shell.editor_stale_result_policy import deliver_revision_gated_editor_result
from app.support.runtime_explainer import build_import_issue_report


class LintWorkflowHost(Protocol):
    def dialog_parent(self) -> Any:
        ...

    def diagnostics_enabled(self) -> bool:
        ...

    def diagnostics_realtime(self) -> bool:
        ...

    def loaded_project(self) -> Any | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, Any]:
        ...

    def editor_buffer_revision(self, file_path: str) -> int | None:
        ...

    def known_runtime_modules(self) -> frozenset[str] | None:
        ...

    def selected_linter(self) -> str:
        ...

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def workflow_broker(self) -> Any:
        ...

    def background_tasks(self) -> Any:
        ...

    def intelligence_metrics_logging_enabled(self) -> bool:
        ...

    def logger(self) -> Any:
        ...

    def open_editor_paths(self) -> list[str]:
        ...

    def editor_manager(self) -> Any:
        ...

    def apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        ...

    def render_merged_problems_panel(self) -> None:
        ...

    def update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        ...

    def stored_lint_diagnostics(self) -> dict[str, list[CodeDiagnostic]]:
        ...

    def problems_panel(self) -> Any | None:
        ...

    def update_problems_tab_title(self, problem_count: int) -> None:
        ...

    def focus_problems_tab(self) -> None:
        ...

    def set_latest_import_issue_report(self, report: object) -> None:
        ...

    def refresh_latest_runtime_issue_report(self) -> None:
        ...

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        ...


class LintWorkflow:
    """Runs Python diagnostics and applies results through the problems controller."""

    def __init__(self, host: LintWorkflowHost) -> None:
        self._host = host

    def render_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        parent = self._host.dialog_parent()
        if not self._host.diagnostics_enabled():
            if trigger == "manual":
                QMessageBox.information(
                    parent,
                    "Lint Current File",
                    "Diagnostics are currently disabled in Settings.",
                )
            return
        if trigger == "realtime" and not self._host.diagnostics_realtime():
            return
        if not file_path.lower().endswith(".py"):
            if trigger == "manual":
                QMessageBox.information(
                    parent,
                    "Lint Current File",
                    "Linting is currently available for Python files only.",
                )
            return
        started_at = time.perf_counter()
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        editor_widgets = self._host.editor_widgets_by_path()
        editor_widget = editor_widgets.get(file_path)
        buffer_source = editor_widget.toPlainText() if editor_widget is not None else None
        buffer_revision = None if editor_widget is None else self._host.editor_buffer_revision(file_path)
        allow_runtime_import_probe = trigger == "manual"
        key = f"lint::{file_path}"

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            project_metadata = None if loaded_project is None else loaded_project.metadata
            _provider, diagnostics = analyze_python_with_workflow(
                self._host.workflow_broker(),
                file_path=file_path,
                project_root=project_root,
                source=buffer_source,
                known_runtime_modules=self._host.known_runtime_modules(),
                allow_runtime_import_probe=allow_runtime_import_probe,
                selected_linter=self._host.selected_linter(),
                lint_rule_overrides=self._host.lint_rule_overrides(),
                project_metadata=project_metadata,
            )
            return diagnostics

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            if editor_widget is None:
                self._host.apply_lint_diagnostics_result(file_path, diagnostics)
                return

            def deliver() -> None:
                if self._host.intelligence_metrics_logging_enabled():
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    if elapsed_ms > 180.0:
                        self._host.logger().warning(
                            "Diagnostics latency warning: file=%s elapsed_ms=%.2f count=%s",
                            file_path,
                            elapsed_ms,
                            len(diagnostics),
                        )
                    else:
                        self._host.logger().info(
                            "Diagnostics telemetry: file=%s elapsed_ms=%.2f count=%s",
                            file_path,
                            elapsed_ms,
                            len(diagnostics),
                        )
                self._host.apply_lint_diagnostics_result(file_path, diagnostics)

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=buffer_revision,
                editor_widget_for_path=lambda path: self._host.editor_widgets_by_path().get(path),
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.logger().warning("Diagnostics run failed for %s: %s", file_path, exc)
            if trigger == "manual":
                QMessageBox.warning(parent, "Lint Current File", f"Diagnostics failed: {exc}")

        self._host.background_tasks().run(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def lint_all_open_files(self) -> None:
        if not self._host.diagnostics_enabled():
            return
        scheduled_any = False
        for file_path in self._host.open_editor_paths():
            if not file_path.lower().endswith(".py"):
                continue
            scheduled_any = True
            self.render_diagnostics_for_file(file_path, trigger="tab_change")
        if not scheduled_any:
            self._host.render_merged_problems_panel()
            active_tab = self._host.editor_manager().active_tab()
            if active_tab is not None:
                active_diags = self._host.stored_lint_diagnostics().get(active_tab.file_path, [])
                self._host.update_status_bar_diagnostics(active_diags)

    def run_import_analysis(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Analyze Imports", "Open a project first.")
            return
        project_root = loaded_project.project_root
        source_overrides: dict[str, str] = {}
        for path, widget in self._host.editor_widgets_by_path().items():
            source_overrides[path] = widget.toPlainText()

        known_modules = self._host.known_runtime_modules()
        lint_rule_overrides = self._host.lint_rule_overrides()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return find_unresolved_imports(
                project_root,
                source_overrides=source_overrides,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
                lint_rule_overrides=lint_rule_overrides,
                project_metadata=loaded_project.metadata,
            )

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            problems_panel = self._host.problems_panel()
            if problems_panel is None:
                return
            _, unresolved_import_severity = resolve_lint_rule_settings("PY200", lint_rule_overrides)
            if unresolved_import_severity == LINT_SEVERITY_ERROR:
                diagnostic_severity = DiagnosticSeverity.ERROR
            elif unresolved_import_severity == LINT_SEVERITY_INFO:
                diagnostic_severity = DiagnosticSeverity.INFO
            else:
                diagnostic_severity = DiagnosticSeverity.WARNING
            import_diags = [
                CodeDiagnostic(
                    code="PY200",
                    severity=diagnostic_severity,
                    file_path=d.file_path,
                    line_number=d.line_number,
                    message=d.message,
                )
                for d in diagnostics
            ]
            problems_panel.set_diagnostics(import_diags)
            self._host.update_problems_tab_title(problems_panel.problem_count())
            self._host.focus_problems_tab()
            import_report = build_import_issue_report(
                project_root,
                diagnostics,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
            )
            self._host.set_latest_import_issue_report(import_report)
            self._host.refresh_latest_runtime_issue_report()
            if import_report.issues:
                self._host.open_runtime_center_dialog(title="Import Analysis", report=import_report)

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Analyze Imports", f"Import analysis failed: {exc}")

        self._host.background_tasks().run(key="analyze_imports", task=task, on_success=on_success, on_error=on_error)


class MainWindowLintHost:
    """Host ports for ``LintWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def diagnostics_enabled(self) -> bool:
        return self._window._diagnostics_enabled

    def diagnostics_realtime(self) -> bool:
        return self._window._diagnostics_realtime

    def loaded_project(self) -> Any | None:
        return self._window._loaded_project

    def editor_widgets_by_path(self) -> dict[str, Any]:
        return self._window._editor_widgets_by_path

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return self._window._editor_tab_workflow.buffer_revision(file_path)

    def known_runtime_modules(self) -> frozenset[str] | None:
        return self._window._known_runtime_modules

    def selected_linter(self) -> str:
        return self._window._selected_linter

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def workflow_broker(self) -> Any:
        return self._window._workflow_broker

    def background_tasks(self) -> Any:
        return self._window._background_tasks

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.metrics_logging_enabled

    def logger(self) -> Any:
        return self._window._logger

    def open_editor_paths(self) -> list[str]:
        return self._window._workspace_controller.open_editor_paths()

    def editor_manager(self) -> Any:
        return self._window._editor_manager

    def apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        self._window._problems_controller.apply_lint_diagnostics_result(file_path, diagnostics)

    def render_merged_problems_panel(self) -> None:
        self._window._problems_controller.render_merged_problems_panel()

    def update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        self._window._problems_controller.update_status_bar_diagnostics(diagnostics)

    def stored_lint_diagnostics(self) -> dict[str, list[CodeDiagnostic]]:
        return self._window._stored_lint_diagnostics

    def problems_panel(self) -> Any | None:
        return self._window._problems_panel

    def update_problems_tab_title(self, problem_count: int) -> None:
        self._window._problems_controller.update_problems_tab_title(problem_count)

    def focus_problems_tab(self) -> None:
        self._window._run_event_workflow.focus_problems_tab()

    def set_latest_import_issue_report(self, report: object) -> None:
        self._window._latest_import_issue_report = report

    def refresh_latest_runtime_issue_report(self) -> None:
        self._window._runtime_onboarding_workflow.refresh_latest_runtime_issue_report()

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        self._window._runtime_onboarding_workflow.open_runtime_center_dialog(
            title=title,
            report=report,
        )


def build_lint_workflow(window: Any) -> LintWorkflow:
    return LintWorkflow(MainWindowLintHost(window))
