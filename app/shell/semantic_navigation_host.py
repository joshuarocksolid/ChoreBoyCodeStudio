"""Host protocol and MainWindow adapter for semantic navigation workflows."""

from __future__ import annotations

from typing import Any, Protocol

from app.editors.code_editor_widget import CodeEditorWidget


class SemanticNavigationHost(Protocol):
    """Narrow host ports for semantic navigation workflows."""

    def dialog_parent(self) -> Any:
        ...

    def loaded_project(self) -> object | None:
        ...

    def editor_manager(self) -> Any:
        ...

    def active_editor_widget(self) -> CodeEditorWidget | None:
        ...

    def editor_widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        ...

    def intelligence_controller(self) -> Any:
        ...

    def editor_buffer_revision(self, file_path: str) -> int | None:
        ...

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        ...

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        ...

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        ...

    def background_tasks(self) -> Any:
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

    def known_runtime_modules(self) -> set[str]:
        ...

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def completion_min_chars(self) -> int:
        ...

    def intelligence_metrics_logging_enabled(self) -> bool:
        ...

    def reported_completion_degradation_reasons(self) -> set[str]:
        ...

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        ...

    def log_warning(self, message: str, *args: object) -> None:
        ...

    def log_info(self, message: str, *args: object) -> None:
        ...

    def runtime_introspection_coordinator(self) -> Any:
        ...

    def flat_outline_symbols_for_path(self, file_path: str, *, fallback_source: str) -> tuple[object, ...]:
        ...

    def save_all_files(self) -> bool:
        ...

    def record_local_history_transaction(
        self,
        payloads_by_path: dict[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        ...

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        ...

    def reload_current_project(self) -> None:
        ...


class MainWindowSemanticNavigationHost:
    """Host ports for semantic navigation workflows backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def loaded_project(self) -> object | None:
        return self._window._loaded_project

    def editor_manager(self) -> Any:
        return self._window._editor_manager

    def active_editor_widget(self) -> CodeEditorWidget | None:
        return self._window._editor_tab_workflow.active_editor_widget()

    def editor_widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        return self._window._editor_widgets_by_path.get(file_path)

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        return self._window._editor_widgets_by_path

    def intelligence_controller(self) -> Any:
        return self._window._intelligence_controller

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return self._window._editor_tab_workflow.buffer_revision(file_path)

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        self._window._editor_tab_workflow.open_file_at_line(file_path, line_number)

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        return self._window._outline_symbols_by_path.get(file_path)

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        self._window._outline_symbols_by_path[file_path] = symbols

    def background_tasks(self) -> Any:
        return self._window._background_tasks

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

    def known_runtime_modules(self) -> set[str]:
        return self._window._known_runtime_modules

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def completion_min_chars(self) -> int:
        return self._window._completion_min_chars

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.metrics_logging_enabled

    def reported_completion_degradation_reasons(self) -> set[str]:
        return self._window._reported_completion_degradation_reasons

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def log_warning(self, message: str, *args: object) -> None:
        self._window._logger.warning(message, *args)

    def log_info(self, message: str, *args: object) -> None:
        self._window._logger.info(message, *args)

    def runtime_introspection_coordinator(self) -> Any:
        return self._window._runtime_introspection_coordinator

    def flat_outline_symbols_for_path(self, file_path: str, *, fallback_source: str) -> tuple[object, ...]:
        return self._window._editor_tab_workflow.flat_outline_symbols_for_path(
            file_path,
            fallback_source=fallback_source,
        )

    def save_all_files(self) -> bool:
        return self._window._save_workflow.handle_save_all_action()

    def record_local_history_transaction(
        self,
        payloads_by_path: dict[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        self._window._local_history_workflow.record_transaction(
            payloads_by_path,
            source=source,
            label=label,
        )

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._window._editor_tab_workflow.refresh_open_tabs_from_disk(file_paths)

    def reload_current_project(self) -> None:
        self._window._project_rescan_workflow.rescan_from_disk(reload_plugins=True, reindex=True)
