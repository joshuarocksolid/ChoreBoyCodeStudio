"""Editor tab lifecycle, preferences, markdown, and external-change polling."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from PySide2.QtCore import QPoint
from PySide2.QtWidgets import QMenu, QTabWidget

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editorconfig import resolve_editorconfig_indentation
from app.editors.indentation import detect_indentation_style_and_size
from app.editors.markdown_editor_pane import MarkdownEditorPane, MarkdownPreviewMode
from app.intelligence.outline_service import OutlineSymbol, build_outline_from_source
from app.project.file_excludes import compute_effective_excludes
from app.project.project_service import enumerate_project_entries
from app.shell.document_safety import DocumentCloseIntent, DocumentScope
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.external_file_change_workflow import ExternalFileChangeWorkflow
from app.shell.project_tree_utils import filter_tree_signature_entries


class EditorTabWorkflowHost(Protocol):
    """Host ports for :class:`EditorTabWorkflow`."""

    def parent_widget(self) -> Any:
        ...

    def editor_tabs_widget(self) -> QTabWidget | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        ...

    def markdown_panes_by_path(self) -> dict[str, MarkdownEditorPane]:
        ...

    def indent_source_by_path(self) -> dict[str, tuple[str, int, str]]:
        ...

    def outline_symbols_by_path(self) -> dict[str, tuple[OutlineSymbol, ...]]:
        ...

    def stored_lint_diagnostics(self) -> dict[str, list[Any]]:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def project_tree_structure_signature(self) -> tuple[str, ...] | None:
        ...

    def set_project_tree_structure_signature(self, signature: tuple[str, ...] | None) -> None:
        ...

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

    def editor_auto_save(self) -> bool:
        ...

    def completion_enabled(self) -> bool:
        ...

    def completion_auto_trigger(self) -> bool:
        ...

    def completion_min_chars(self) -> int:
        ...

    def intelligence_runtime_settings(self) -> Any:
        ...

    def outline_panel(self) -> Any | None:
        ...

    def outline_follow_cursor(self) -> bool:
        ...

    def status_controller(self) -> Any | None:
        ...

    def menu_registry(self) -> Any | None:
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

    def stop_outline_refresh_timer(self) -> None:
        ...

    def start_outline_refresh_timer(self) -> None:
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

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
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


class EditorTabWorkflow:
    """Owns editor tab lifecycle, buffer sync hooks, markdown mode, and zoom."""

    def __init__(
        self,
        *,
        host: EditorTabWorkflowHost,
        editor_manager: EditorManager,
        editor_tabs_coordinator: EditorTabsCoordinator,
        save_workflow: Any,
        local_history_workflow: Any,
        debug_control_workflow: Any,
        external_file_change_workflow: ExternalFileChangeWorkflow,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._save_workflow = save_workflow
        self._local_history_workflow = local_history_workflow
        self._debug_control_workflow = debug_control_workflow
        self._external_file_change_workflow = external_file_change_workflow

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def release_editor_widget(self, widget: CodeEditorWidget) -> None:
        if self._host.debug_execution_editor() is widget:
            self._host.clear_debug_execution_indicator()
        markdown_panes = self._host.markdown_panes_by_path()
        for file_path, markdown_pane in list(markdown_panes.items()):
            if markdown_pane.source_editor() is widget:
                markdown_panes.pop(file_path, None)
                markdown_pane.deleteLater()
                return
        widget.deleteLater()

    def refresh_outline_for_active_tab(self) -> None:
        outline_panel = self._host.outline_panel()
        if outline_panel is None:
            return
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            outline_panel.set_unsupported_language("python")
            return
        file_path = active_tab.file_path
        if Path(file_path).suffix.lower() not in {".py", ".pyw", ".pyi"}:
            outline_panel.set_unsupported_language(
                Path(file_path).suffix.lstrip(".") or "this"
            )
            self._host.outline_symbols_by_path().pop(file_path, None)
            return
        editor_widget = self._host.editor_widgets_by_path().get(
            str(Path(file_path).expanduser().resolve())
        )
        source = editor_widget.toPlainText() if editor_widget is not None else active_tab.current_content
        symbols = build_outline_from_source(source or "")
        self._host.outline_symbols_by_path()[file_path] = symbols
        outline_panel.set_outline(symbols, file_path)
        if editor_widget is not None and self._host.outline_follow_cursor():
            line_number = editor_widget.textCursor().blockNumber() + 1
            outline_panel.highlight_symbol_at_line(line_number)

    def handle_outline_symbol_activated(self, file_path: str, line_number: int) -> None:
        self.open_file_at_line(file_path, line_number)

    def open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        if not self._host.editor_tab_factory().open_file_in_editor(file_path, preview=preview):
            return
        editor_widget = self._host.editor_widgets_by_path().get(
            str(Path(file_path).expanduser().resolve())
        )
        if editor_widget is None or line_number is None:
            return
        editor_widget.go_to_line(line_number)

    def tab_index_for_path(self, file_path: str) -> int:
        return self._editor_tabs_coordinator.tab_index_for_path(file_path)

    def remove_tab_widget_for_path(self, file_path: str) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        tab_index = self.tab_index_for_path(file_path)
        if tab_index < 0:
            return
        editor_tabs_widget.removeTab(tab_index)
        widget = self._host.workspace_controller().pop_editor(file_path)
        if widget is not None:
            self.release_editor_widget(widget)
        self._host.indent_source_by_path().pop(file_path, None)
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        status_controller = self._host.status_controller()
        if editor_tabs_widget.count() == 0 and status_controller is not None:
            status_controller.set_indent_status(style=None, size=None, source=None)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._editor_tabs_coordinator.refresh_tab_presentation(file_path)

    def promote_preview_tab(self, file_path: str) -> bool:
        return self._editor_tabs_coordinator.promote_preview_tab(file_path)

    def promote_existing_preview_tab(self) -> bool:
        return self._editor_tabs_coordinator.promote_existing_preview_tab()

    def active_markdown_pane(self) -> MarkdownEditorPane | None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self._host.markdown_panes_by_path().get(active_tab.file_path)

    def set_active_markdown_mode(self, mode: str) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.set_mode(mode)
        self.refresh_markdown_action_states()

    def handle_markdown_show_source_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.SOURCE)

    def handle_markdown_show_preview_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.PREVIEW)

    def handle_markdown_show_split_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.SPLIT)

    def handle_markdown_toggle_preview_action(self) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.toggle_preview()
        self.refresh_markdown_action_states()

    def refresh_markdown_action_states(self) -> None:
        menu_registry = self._host.menu_registry()
        if menu_registry is None:
            return
        markdown_pane = self.active_markdown_pane()
        enabled = markdown_pane is not None
        for action_id in (
            "shell.action.view.markdownTogglePreview",
            "shell.action.view.markdownShowSource",
            "shell.action.view.markdownShowPreview",
            "shell.action.view.markdownShowSplit",
        ):
            action = menu_registry.action(action_id)
            if action is not None:
                action.setEnabled(enabled)

    def handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        if self._editor_manager.get_tab(file_path) is None:
            return
        self.advance_buffer_revision(file_path)
        tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if tab_state.is_preview and tab_state.is_dirty:
            self.promote_preview_tab(file_path)
            refreshed_state = self._editor_manager.get_tab(file_path)
            if refreshed_state is not None:
                tab_state = refreshed_state
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return

        tab_index = self.tab_index_for_path(tab_state.file_path)
        if tab_index < 0:
            return
        self.refresh_tab_presentation(tab_state.file_path)
        if tab_state.is_dirty:
            self._host.local_history_schedule_autosave(tab_state.file_path, tab_state.current_content)
            if self._host.editor_auto_save():
                self._host.start_auto_save_to_file_timer()
        else:
            self._host.local_history_discard_pending_autosave(tab_state.file_path)
            self._host.local_history_delete_draft(tab_state.file_path)
        self._host.refresh_save_action_states()
        self.update_editor_status_for_path(tab_state.file_path)
        if not self._host.is_shutting_down():
            self._host.diagnostics_schedule_realtime_lint(tab_state.file_path)
        self._host.start_outline_refresh_timer()

    def handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        status_controller = self._host.status_controller()
        if tab_state is None or status_controller is None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=line_number,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )
        outline_panel = self._host.outline_panel()
        if outline_panel is not None and self._host.outline_follow_cursor():
            outline_panel.highlight_symbol_at_line(line_number)

    def update_editor_status_for_path(self, file_path: str) -> None:
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widgets_by_path().get(file_path)
        if tab_state is None or editor_widget is None:
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            return
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )

    def active_editor_widget(self) -> CodeEditorWidget | None:
        return self._editor_tabs_coordinator.active_editor_widget()  # type: ignore[return-value]

    def advance_buffer_revision(self, file_path: str) -> int:
        return self._editor_tabs_coordinator.advance_buffer_revision(file_path)

    def buffer_revision(self, file_path: str) -> int | None:
        return self._editor_tabs_coordinator.buffer_revision(file_path)

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if tab_index < 0 or editor_tabs_widget is None:
            return

        tab_path = editor_tabs_widget.tabToolTip(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self.refresh_markdown_action_states()
        self.update_editor_status_for_path(tab_path)
        self.update_indent_status_for_path(tab_path)
        self.check_for_external_file_change(tab_path)
        self._host.render_lint_diagnostics_for_file(tab_path, trigger="tab_change")
        self._host.stop_outline_refresh_timer()
        self.refresh_outline_for_active_tab()
        self._host.reveal_project_tree_path(tab_path)

    def handle_editor_tab_header_double_click(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        file_path = editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return
        self.promote_preview_tab(file_path)

    def handle_keep_preview_open_shortcut(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return
        if not active_tab.is_preview:
            return
        self.promote_preview_tab(active_tab.file_path)

    def show_editor_tab_context_menu(self, position: QPoint) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        tab_bar = editor_tabs_widget.tabBar()
        tab_index = tab_bar.tabAt(position)
        if tab_index < 0:
            return
        file_path = editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return

        menu = QMenu(self._host.parent_widget())
        markdown_source_action = None
        markdown_preview_action = None
        markdown_split_action = None
        markdown_pane = self._host.markdown_panes_by_path().get(file_path)
        if markdown_pane is not None:
            markdown_source_action = menu.addAction("Markdown: Show Source")
            markdown_preview_action = menu.addAction("Markdown: Show Preview")
            markdown_split_action = menu.addAction("Markdown: Show Split View")
            menu.addSeparator()
        local_history_action = menu.addAction("Local History...")
        menu.addSeparator()
        close_action = menu.addAction("Close")
        chosen = menu.exec_(tab_bar.mapToGlobal(position))
        if markdown_pane is not None and chosen == markdown_source_action:
            markdown_pane.set_mode(MarkdownPreviewMode.SOURCE)
            self.refresh_markdown_action_states()
        elif markdown_pane is not None and chosen == markdown_preview_action:
            markdown_pane.set_mode(MarkdownPreviewMode.PREVIEW)
            self.refresh_markdown_action_states()
        elif markdown_pane is not None and chosen == markdown_split_action:
            markdown_pane.set_mode(MarkdownPreviewMode.SPLIT)
            self.refresh_markdown_action_states()
        elif chosen == local_history_action:
            self._host.show_local_history_for_path(file_path)
        elif chosen == close_action:
            self.handle_tab_close_requested(tab_index)

    def handle_tab_close_requested(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        file_path = editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return

        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is not None and tab_state.is_dirty:
            decision = self._save_workflow.request_unsaved_changes_decision(
                "closing this tab",
                scope=DocumentScope.TAB,
                allow_keep_for_next_launch=False,
                dirty_buffers=(tab_state,),
            )
            if decision.intent is DocumentCloseIntent.CANCEL:
                return
            if not self._save_workflow.apply_unsaved_changes_decision(decision):
                return

        editor_tabs_widget.removeTab(tab_index)
        widget = self._host.workspace_controller().pop_editor(file_path)
        if widget is not None:
            self.release_editor_widget(widget)
        self._editor_manager.close_file(file_path)
        self._debug_control_workflow.breakpoint_store.clear_file(file_path)
        self._host.stored_lint_diagnostics().pop(file_path, None)
        self._host.render_merged_problems_panel()
        self._debug_control_workflow.refresh_breakpoints_list()
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self.refresh_markdown_action_states()

    def close_active_tab(self) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        tab_index = editor_tabs_widget.currentIndex()
        if tab_index >= 0:
            self.handle_tab_close_requested(tab_index)

    def reset_editor_tabs(self) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is not None:
            for path in list(self._host.workspace_controller().open_editor_paths()):
                widget = self._host.workspace_controller().pop_editor(path)
                if widget is not None:
                    self.release_editor_widget(widget)
            editor_tabs_widget.clear()
        self._host.local_history_stop_autosave_timer()
        self._host.stop_auto_save_to_file_timer()
        self._host.stop_realtime_lint_timer()
        self._host.local_history_clear_pending_autosaves()
        self._host.clear_pending_realtime_lint_file_path()
        self._host.clear_debug_execution_indicator()
        self._host.workspace_controller().clear()
        replacement_manager = EditorManager()
        self._host.replace_editor_manager(replacement_manager)
        self.set_editor_manager(replacement_manager)
        self._host.markdown_panes_by_path().clear()
        self._host.indent_source_by_path().clear()
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self.refresh_markdown_action_states()
        status_controller = self._host.status_controller()
        if status_controller is not None:
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            status_controller.set_indent_status(style=None, size=None, source=None)

    def effective_font_size(self) -> int:
        return max(8, min(72, self._host.editor_font_size() + self._host.zoom_delta()))

    def apply_editor_preferences_to_open_editors(self) -> None:
        effective_size = self.effective_font_size()
        for file_path, editor_widget in self._host.editor_widgets_by_path().items():
            editor_widget.set_editor_preferences(
                tab_width=self._host.editor_tab_width(),
                font_point_size=effective_size,
                font_family=self._host.editor_font_family(),
                indent_style=self._host.editor_indent_style(),
                indent_size=self._host.editor_indent_size(),
                hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
                auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
            )
            self.apply_detected_indentation_for_widget(file_path, editor_widget, editor_widget.toPlainText())
            editor_widget.set_completion_preferences(
                enabled=self._host.completion_enabled(),
                auto_trigger=self._host.completion_auto_trigger(),
                min_chars=self._host.completion_min_chars(),
            )

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        for editor_widget in self._host.editor_widgets_by_path().values():
            self.apply_runtime_intelligence_preferences_to_editor(editor_widget)

    def apply_runtime_intelligence_preferences_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        runtime_settings = self._host.intelligence_runtime_settings()
        editor_widget.set_metrics_logging_enabled(runtime_settings.metrics_logging_enabled)
        editor_widget.set_highlighting_policy(
            adaptive_mode=runtime_settings.highlighting_adaptive_mode,
            reduced_threshold_chars=runtime_settings.highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=runtime_settings.highlighting_lexical_only_threshold_chars,
        )

    def apply_detected_indentation_for_widget(
        self,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
    ) -> None:
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        editorconfig_indent = resolve_editorconfig_indentation(file_path, project_root=project_root)
        if editorconfig_indent is not None:
            effective_style = editorconfig_indent.indent_style
            effective_size = max(1, editorconfig_indent.indent_size)
            editor_widget.set_editor_preferences(
                tab_width=max(1, editorconfig_indent.tab_width),
                font_point_size=self.effective_font_size(),
                font_family=self._host.editor_font_family(),
                indent_style=effective_style,
                indent_size=effective_size,
                hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
                auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
            )
            self.record_indent_source(file_path, effective_style, effective_size, "editorconfig")
            return
        if not self._host.editor_detect_indentation_from_file() or not file_path.lower().endswith(
            (".py", ".json", ".md", ".txt")
        ):
            self.record_indent_source(
                file_path, self._host.editor_indent_style(), self._host.editor_indent_size(), "user"
            )
            return
        detected = detect_indentation_style_and_size(source_text)
        if detected is None:
            self.record_indent_source(
                file_path, self._host.editor_indent_style(), self._host.editor_indent_size(), "user"
            )
            return
        style, size = detected
        editor_widget.set_editor_preferences(
            tab_width=self._host.editor_tab_width(),
            font_point_size=self.effective_font_size(),
            font_family=self._host.editor_font_family(),
            indent_style=style,
            indent_size=size,
            hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
            auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
        )
        self.record_indent_source(file_path, style, size, "auto")

    def record_indent_source(
        self,
        file_path: str,
        style: str,
        size: int,
        source: str,
    ) -> None:
        self._host.indent_source_by_path()[file_path] = (style, int(size), source)
        active_tab = self._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self.update_indent_status_for_path(file_path)

    def update_indent_status_for_path(self, file_path: str | None) -> None:
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        if file_path is None:
            status_controller.set_indent_status(style=None, size=None, source=None)
            return
        record = self._host.indent_source_by_path().get(file_path)
        if record is None:
            status_controller.set_indent_status(style=None, size=None, source=None)
            return
        style, size, source = record
        status_controller.set_indent_status(style=style, size=size, source=source)

    def handle_zoom_in(self) -> None:
        if self._host.editor_font_size() + self._host.zoom_delta() < 72:
            self._host.set_zoom_delta(self._host.zoom_delta() + 1)
            self.apply_editor_preferences_to_open_editors()

    def handle_zoom_out(self) -> None:
        if self._host.editor_font_size() + self._host.zoom_delta() > 8:
            self._host.set_zoom_delta(self._host.zoom_delta() - 1)
            self.apply_editor_preferences_to_open_editors()

    def handle_zoom_reset(self) -> None:
        if self._host.zoom_delta() != 0:
            self._host.set_zoom_delta(0)
            self.apply_editor_preferences_to_open_editors()

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        for file_path in file_paths:
            tab_state = self._editor_manager.get_tab(file_path)
            editor_widget = self._host.editor_widgets_by_path().get(file_path)
            if tab_state is None or editor_widget is None:
                continue
            try:
                refreshed = Path(file_path).read_text(encoding="utf-8")
            except OSError:
                continue
            editor_widget.blockSignals(True)
            editor_widget.setPlainText(refreshed)
            editor_widget.blockSignals(False)
            self.advance_buffer_revision(file_path)
            self.apply_detected_indentation_for_widget(file_path, editor_widget, refreshed)
            updated_tab = self._editor_manager.update_tab_content(file_path, refreshed)
            updated_tab.mark_saved(last_known_mtime=self._editor_manager.current_disk_mtime(file_path))
            tab_index = self.tab_index_for_path(file_path)
            editor_tabs_widget = self._host.editor_tabs_widget()
            if editor_tabs_widget is not None and tab_index >= 0:
                self.refresh_tab_presentation(file_path)
        self._host.refresh_save_action_states()

    def check_for_external_file_change(self, file_path: str) -> None:
        self._external_file_change_workflow.check_and_handle(file_path)

    def poll_external_file_changes(self) -> None:
        stale_paths = self._editor_manager.stale_open_paths()
        if stale_paths:
            active_tab = self._editor_manager.active_tab()
            if active_tab is not None and active_tab.file_path in stale_paths:
                self.check_for_external_file_change(active_tab.file_path)

        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return
        current_signature = self.scan_project_tree_signature(loaded_project)
        previous_signature = self._host.project_tree_structure_signature()
        if previous_signature is None:
            self._host.set_project_tree_structure_signature(current_signature)
            return
        if current_signature == previous_signature:
            return
        self._host.set_project_tree_structure_signature(current_signature)
        self._host.reload_current_project()

    def scan_project_tree_signature(self, loaded_project: LoadedProject) -> tuple[str, ...]:
        layered_excludes = self._host.load_effective_exclude_patterns(loaded_project.project_root)
        effective_excludes = compute_effective_excludes(
            layered_excludes,
            loaded_project.metadata.exclude_patterns,
        )
        entries = enumerate_project_entries(
            loaded_project.project_root,
            exclude_patterns=effective_excludes,
        )
        return filter_tree_signature_entries(tuple(entry.relative_path for entry in entries))


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
        return self._window._markdown_panes_by_path

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


def build_editor_tab_workflow(window: Any) -> EditorTabWorkflow:
    """Construct :class:`EditorTabWorkflow` for a ``MainWindow`` instance."""
    workflow = EditorTabWorkflow(
        host=MainWindowEditorTabHost(window),
        editor_manager=window._editor_manager,
        editor_tabs_coordinator=window._editor_tabs_coordinator,
        save_workflow=window._save_workflow,
        local_history_workflow=window._local_history_workflow,
        debug_control_workflow=window._debug_control_workflow,
        external_file_change_workflow=window._external_file_change_workflow,
    )
    return workflow
