"""MainWindow adapter ports for :class:`EditorTabWorkflow`."""

from __future__ import annotations

from typing import Any

from PySide2.QtWidgets import QTabWidget

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.intelligence.outline_service import OutlineSymbol


class MainWindowEditorTabHost:
    """Host ports for ``EditorTabWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def parent_widget(self) -> Any:
        return self._window

    def editor_tabs_widget(self) -> QTabWidget | None:
        return self._window._editor_tabs_widget

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        return self._window._editor_widgets_by_path

    def markdown_panes_by_path(self) -> dict[str, MarkdownEditorPane]:
        return self._window._tab_content_registry.markdown_panes_by_path

    def tab_content_registry(self) -> Any:
        return self._window._tab_content_registry

    def indent_source_by_path(self) -> dict[str, tuple[str, int, str]]:
        return self._window._indent_source_by_path

    def outline_symbols_by_path(self) -> dict[str, tuple[OutlineSymbol, ...]]:
        return self._window._outline_symbols_by_path

    def stored_lint_diagnostics(self) -> dict[str, list[Any]]:
        return self._window._stored_lint_diagnostics

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def project_tree_structure_signature(self) -> tuple[str, ...] | None:
        return self._window._project_tree_structure_signature

    def set_project_tree_structure_signature(self, signature: tuple[str, ...] | None) -> None:
        self._window._project_tree_structure_signature = signature
        if signature is not None:
            self._window._project_inventory_orchestrator.set_tree_structure_signature(signature)

    def project_inventory_generation(self) -> int:
        return self._window._project_inventory_orchestrator.generation

    def project_inventory_tree_signature(self) -> tuple[str, ...] | None:
        return self._window._project_inventory_orchestrator.tree_structure_signature()

    def editor_tab_width(self) -> int:
        return self._window._editor_tab_width

    def editor_font_size(self) -> int:
        return self._window._editor_font_size

    def zoom_delta(self) -> int:
        return self._window._zoom_delta

    def set_zoom_delta(self, delta: int) -> None:
        self._window._zoom_delta = delta

    def editor_font_family(self) -> str:
        return self._window._editor_font_family

    def editor_indent_style(self) -> str:
        return self._window._editor_indent_style

    def editor_indent_size(self) -> int:
        return self._window._editor_indent_size

    def editor_detect_indentation_from_file(self) -> bool:
        return self._window._editor_detect_indentation_from_file

    def editor_hover_tooltip_enabled(self) -> bool:
        return self._window._editor_hover_tooltip_enabled

    def editor_auto_reindent_flat_python_paste(self) -> bool:
        return self._window._editor_auto_reindent_flat_python_paste

    def editor_auto_save(self) -> bool:
        return self._window._editor_auto_save

    def completion_enabled(self) -> bool:
        return self._window._completion_enabled

    def completion_auto_trigger(self) -> bool:
        return self._window._completion_auto_trigger

    def completion_min_chars(self) -> int:
        return self._window._completion_min_chars

    def intelligence_runtime_settings(self) -> Any:
        return self._window._intelligence_runtime_settings

    def outline_panel(self) -> Any | None:
        return self._window._outline_panel

    def outline_follow_cursor(self) -> bool:
        return self._window._outline_follow_cursor

    def background_tasks(self) -> Any:
        return self._window._background_tasks

    def status_controller(self) -> Any | None:
        return self._window._status_controller

    def menu_registry(self) -> Any | None:
        return self._window._menu_registry

    def is_shutting_down(self) -> bool:
        return self._window._is_shutting_down

    def debug_execution_editor(self) -> CodeEditorWidget | None:
        return self._window._debug_execution_editor

    def set_debug_execution_editor(self, editor: CodeEditorWidget | None) -> None:
        self._window._debug_execution_editor = editor

    def workspace_controller(self) -> Any:
        return self._window._workspace_controller

    def replace_editor_manager(self, editor_manager: EditorManager) -> None:
        self._window._editor_manager = editor_manager
        self._window._local_history_workflow.set_editor_manager(editor_manager)

    def start_auto_save_to_file_timer(self) -> None:
        self._window._auto_save_to_file_timer.start()

    def stop_auto_save_to_file_timer(self) -> None:
        self._window._auto_save_to_file_timer.stop()

    def stop_realtime_lint_timer(self) -> None:
        self._window._realtime_lint_timer.stop()

    def stop_outline_refresh_timer(self) -> None:
        self._window._outline_refresh_timer.stop()

    def start_outline_refresh_timer(self) -> None:
        self._window._outline_refresh_timer.start()

    def clear_pending_realtime_lint_file_path(self) -> None:
        self._window._pending_realtime_lint_file_path = None

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def refresh_run_action_states(self) -> None:
        self._window._run_event_workflow.refresh_run_action_states()

    def render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        self._window._lint_workflow.render_diagnostics_for_file(file_path, trigger=trigger)

    def render_merged_problems_panel(self) -> None:
        self._window._problems_controller.render_merged_problems_panel()

    def reveal_project_tree_path(self, file_path: str) -> None:
        self._window._project_tree_presenter.reveal_path(file_path)

    def reload_current_project(self) -> None:
        self._window._project_tree_ui_workflow.reload_current_project()

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        self._window._project_rescan_workflow.rescan_from_disk(
            reload_plugins=reload_plugins,
            reindex=reindex,
        )

    def project_python_paths_fingerprint(self) -> tuple[str, ...] | None:
        return self._window._project_inventory_orchestrator.python_paths_fingerprint()

    def start_symbol_indexing_for_loaded_project(self) -> None:
        loaded_project = self._window._loaded_project
        if loaded_project is None:
            return
        self._window._intelligence_cache_workflow.start_symbol_indexing(
            loaded_project.project_root,
            inventory_snapshot=self._window._project_inventory_orchestrator.snapshot,
        )

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return self._window._file_project_commands_workflow.load_effective_exclude_patterns(project_root)

    def clear_debug_execution_indicator(self) -> None:
        self._window._debug_inspector_workflow.clear_debug_execution_indicator()

    def editor_tab_factory(self) -> Any:
        return self._window._editor_tab_factory

    def show_local_history_for_path(self, file_path: str) -> None:
        self._window._local_history_workflow.show_local_history_for_path(file_path)

    def local_history_stop_autosave_timer(self) -> None:
        self._window._local_history_workflow.stop_autosave_timer()

    def local_history_clear_pending_autosaves(self) -> None:
        self._window._local_history_workflow.clear_pending_autosaves()

    def local_history_schedule_autosave(self, file_path: str, content: str) -> None:
        self._window._local_history_workflow.schedule_autosave(file_path, content)

    def local_history_discard_pending_autosave(self, file_path: str) -> None:
        self._window._local_history_workflow.discard_pending_autosave(file_path)

    def local_history_delete_draft(self, file_path: str) -> None:
        self._window._local_history_workflow.delete_draft(file_path)

    def diagnostics_schedule_realtime_lint(self, file_path: str) -> None:
        self._window._diagnostics_orchestrator.schedule_realtime_lint(file_path)


__all__ = ["MainWindowEditorTabHost"]
