"""Python lint execution and diagnostics result application for the shell."""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from PySide2.QtWidgets import QMessageBox

from app.intelligence.diagnostics_service import CodeDiagnostic
from app.plugins.workflow_adapters import analyze_python_with_workflow


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
            active_widget = self._host.editor_widgets_by_path().get(file_path)
            if editor_widget is not None and active_widget is not editor_widget:
                return
            if buffer_revision is not None and self._host.editor_buffer_revision(file_path) != buffer_revision:
                self._host.logger().info(
                    "Dropped stale diagnostics result for %s due to buffer revision change.",
                    file_path,
                )
                return
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


def build_lint_workflow(window: Any) -> LintWorkflow:
    return LintWorkflow(MainWindowLintHost(window))
