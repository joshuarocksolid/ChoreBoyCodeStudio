"""Typed host sub-protocols for :class:`EditorTabWorkflow` decomposition."""

from __future__ import annotations

from typing import Any, Protocol

from PySide2.QtWidgets import QTabWidget

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.intelligence.outline_service import OutlineSymbol


class EditorTabOutlineHost(Protocol):
    """Outline debounce, symbol cache, and async refresh hooks."""

    def outline_panel(self) -> Any | None:
        ...

    def outline_follow_cursor(self) -> bool:
        ...

    def outline_symbols_by_path(self) -> dict[str, tuple[OutlineSymbol, ...]]:
        ...

    def background_tasks(self) -> Any:
        ...

    def stop_outline_refresh_timer(self) -> None:
        ...

    def start_outline_refresh_timer(self) -> None:
        ...


class EditorTabPollHost(Protocol):
    """External-change poll tick, tree signature compare, and rescan triggers."""

    def loaded_project(self) -> LoadedProject | None:
        ...

    def project_tree_structure_signature(self) -> tuple[str, ...] | None:
        ...

    def set_project_tree_structure_signature(self, signature: tuple[str, ...] | None) -> None:
        ...

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        ...

    def project_python_paths_fingerprint(self) -> tuple[str, ...] | None:
        ...

    def start_symbol_indexing_for_loaded_project(self) -> None:
        ...

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        ...

    def project_inventory_generation(self) -> int:
        ...

    def project_inventory_tree_signature(self) -> tuple[str, ...] | None:
        ...


class EditorTabPreferencesHost(Protocol):
    """Zoom, indent detection, editor prefs, and completion settings."""

    def editor_tab_width(self) -> int:
        ...

    def editor_font_size(self) -> int:
        ...

    def zoom_delta(self) -> int:
        ...

    def set_zoom_delta(self, delta: int) -> None:
        ...

    def editor_font_family(self) -> str:
        ...

    def editor_indent_style(self) -> str:
        ...

    def editor_indent_size(self) -> int:
        ...

    def editor_detect_indentation_from_file(self) -> bool:
        ...

    def editor_hover_tooltip_enabled(self) -> bool:
        ...

    def editor_auto_reindent_flat_python_paste(self) -> bool:
        ...

    def completion_enabled(self) -> bool:
        ...

    def completion_auto_trigger(self) -> bool:
        ...

    def completion_min_chars(self) -> int:
        ...

    def intelligence_runtime_settings(self) -> Any:
        ...

    def indent_source_by_path(self) -> dict[str, tuple[str, int, str]]:
        ...


class EditorTabMarkdownHost(Protocol):
    """Markdown pane registry and view action menu accessors."""

    def markdown_panes_by_path(self) -> dict[str, MarkdownEditorPane]:
        ...

    def menu_registry(self) -> Any | None:
        ...


class EditorTabWorkflowHost(
    EditorTabOutlineHost,
    EditorTabPollHost,
    EditorTabPreferencesHost,
    EditorTabMarkdownHost,
    Protocol,
):
    """Composite host ports for :class:`EditorTabWorkflow`."""

    def parent_widget(self) -> Any:
        ...

    def editor_tabs_widget(self) -> QTabWidget | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        ...

    def stored_lint_diagnostics(self) -> dict[str, list[Any]]:
        ...

    def editor_auto_save(self) -> bool:
        ...

    def status_controller(self) -> Any | None:
        ...

    def is_shutting_down(self) -> bool:
        ...

    def debug_execution_editor(self) -> CodeEditorWidget | None:
        ...

    def set_debug_execution_editor(self, editor: CodeEditorWidget | None) -> None:
        ...

    def workspace_controller(self) -> Any:
        ...

    def replace_editor_manager(self, editor_manager: EditorManager) -> None:
        ...

    def start_auto_save_to_file_timer(self) -> None:
        ...

    def stop_auto_save_to_file_timer(self) -> None:
        ...

    def stop_realtime_lint_timer(self) -> None:
        ...

    def clear_pending_realtime_lint_file_path(self) -> None:
        ...

    def refresh_save_action_states(self) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        ...

    def render_merged_problems_panel(self) -> None:
        ...

    def reveal_project_tree_path(self, file_path: str) -> None:
        ...

    def reload_current_project(self) -> None:
        ...

    def editor_tab_factory(self) -> Any:
        ...

    def clear_debug_execution_indicator(self) -> None:
        ...

    def show_local_history_for_path(self, file_path: str) -> None:
        ...

    def local_history_stop_autosave_timer(self) -> None:
        ...

    def local_history_clear_pending_autosaves(self) -> None:
        ...

    def local_history_schedule_autosave(self, file_path: str, content: str) -> None:
        ...

    def local_history_discard_pending_autosave(self, file_path: str) -> None:
        ...

    def local_history_delete_draft(self, file_path: str) -> None:
        ...

    def diagnostics_schedule_realtime_lint(self, file_path: str) -> None:
        ...


__all__ = [
    "EditorTabMarkdownHost",
    "EditorTabOutlineHost",
    "EditorTabPollHost",
    "EditorTabPreferencesHost",
    "EditorTabWorkflowHost",
]
