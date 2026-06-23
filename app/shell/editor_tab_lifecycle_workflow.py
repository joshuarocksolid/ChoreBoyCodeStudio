"""Editor tab close, reset, context menu, and preview promotion hooks."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QPoint
from PySide2.QtWidgets import QMenu

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.shell.document_safety import DocumentCloseIntent, DocumentScope
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost
from app.shell.markdown_tab_registry import MarkdownTabRegistry, release_editor_widget


class EditorTabLifecycleWorkflow:
    """Owns tab removal, close prompts, reset, and tab-bar context menus."""

    def __init__(
        self,
        *,
        host: EditorTabWorkflowHost,
        editor_manager: EditorManager,
        editor_tabs_coordinator: Any,
        save_workflow: Any,
        debug_control_workflow: Any,
        markdown_registry: MarkdownTabRegistry,
        markdown_workflow: Any,
        tab_workflow: Any,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._save_workflow = save_workflow
        self._debug_control_workflow = debug_control_workflow
        self._markdown_registry = markdown_registry
        self._markdown_workflow = markdown_workflow
        self._tab_workflow = tab_workflow

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def release_editor_widget(self, widget: CodeEditorWidget) -> None:
        release_editor_widget(
            widget,
            registry=self._markdown_registry,
            is_debug_execution_editor=lambda candidate: self._host.debug_execution_editor() is candidate,
            clear_debug_execution_indicator=self._host.clear_debug_execution_indicator,
        )

    def remove_tab_widget_for_path(self, file_path: str) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        tab_index = self._editor_tabs_coordinator.tab_index_for_path(file_path)
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

    def handle_editor_tab_header_double_click(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        file_path = editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return
        self._editor_tabs_coordinator.promote_preview_tab(file_path)

    def handle_keep_preview_open_shortcut(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return
        if not active_tab.is_preview:
            return
        self._editor_tabs_coordinator.promote_preview_tab(active_tab.file_path)

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
        markdown_source_action, markdown_preview_action, markdown_split_action = (
            self._markdown_workflow.append_context_menu_actions(menu, file_path)
        )
        markdown_pane = self._markdown_registry.pane_for_path(file_path)
        local_history_action = menu.addAction("Local History...")
        menu.addSeparator()
        close_action = menu.addAction("Close")
        chosen = menu.exec_(tab_bar.mapToGlobal(position))
        if self._markdown_workflow.handle_context_menu_choice(
            markdown_pane=markdown_pane,
            chosen=chosen,
            markdown_source_action=markdown_source_action,
            markdown_preview_action=markdown_preview_action,
            markdown_split_action=markdown_split_action,
        ):
            return
        if chosen == local_history_action:
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
        self._markdown_workflow.refresh_markdown_action_states()

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
        self._host.stop_outline_refresh_timer()
        self._host.outline_symbols_by_path().clear()
        outline_panel = self._host.outline_panel()
        if outline_panel is not None:
            outline_panel.set_outline([], "")
        self._host.local_history_clear_pending_autosaves()
        self._host.clear_pending_realtime_lint_file_path()
        self._host.clear_debug_execution_indicator()
        self._host.workspace_controller().clear()
        replacement_manager = EditorManager()
        self._host.replace_editor_manager(replacement_manager)
        self._tab_workflow.set_editor_manager(replacement_manager)
        self._markdown_workflow.clear_registry()
        self._host.indent_source_by_path().clear()
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self._markdown_workflow.refresh_markdown_action_states()
        status_controller = self._host.status_controller()
        if status_controller is not None:
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            status_controller.set_indent_status(style=None, size=None, source=None)


__all__ = ["EditorTabLifecycleWorkflow"]
