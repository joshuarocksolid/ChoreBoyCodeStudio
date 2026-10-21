"""Editor-tab presentation and state coordination helpers."""

from __future__ import annotations

from typing import Any

from PySide2.QtWidgets import QInputDialog, QMessageBox, QTabWidget, QWidget

from app.core import constants
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING, EditorTabState
from app.editors.text_editing import FlatPythonIndentRepairResult
from app.features.markdown.markdown_editor_pane import MarkdownEditorPane
from app.shell.editor_tab_bar import MiddleClickTabBar, editor_tab_tooltip, tab_disk_state
from app.shell.editor_tab_page import EditorTabPage


def _index_of_buffer(tabs: QTabWidget, buffer_id: str) -> int:
    tab_bar = tabs.tabBar()
    for index in range(tabs.count()):
        data = tab_bar.tabData(index)
        if isinstance(data, dict) and data.get("buffer_id") == buffer_id:
            return index
    return -1


def tab_presentation_data(tab_state: EditorTabState) -> dict[str, object]:
    conflict_kind = None if tab_state.disk_conflict is None else tab_state.disk_conflict.kind
    return {
        "buffer_id": tab_state.buffer_id,
        "file_path": tab_state.file_path,
        "is_preview": tab_state.is_preview,
        "is_stale": conflict_kind == DISK_CONFLICT_CHANGED,
        "is_missing": conflict_kind == DISK_CONFLICT_MISSING,
    }


class EditorTabsCoordinator:
    """Keeps editor-manager tab state and Qt tab chrome in sync."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def tab_index_for_path(self, file_path: str) -> int:
        tab_state = self._window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return -1
        return self.tab_index_for_buffer_id(tab_state.buffer_id)

    def file_path_for_tab_index(self, tab_index: int) -> str | None:
        window = self._window
        widget = window._editor_tabs_widget
        if widget is None or tab_index < 0 or tab_index >= widget.count():
            return None
        data = widget.tabBar().tabData(tab_index)
        if not isinstance(data, dict):
            return None
        buffer_id = data.get("buffer_id")
        if not isinstance(buffer_id, str):
            return None
        tab_state = window._editor_manager.get_tab_by_id(buffer_id)
        if tab_state is None:
            return None
        return tab_state.file_path

    def tab_index_for_buffer_id(self, buffer_id: str) -> int:
        """Index of the buffer's tab in the focused group, or -1."""
        window = self._window
        if window._editor_tabs_widget is None:
            return -1
        return _index_of_buffer(window._editor_tabs_widget, buffer_id)

    def tab_index_in(self, tabs: QTabWidget, buffer_id: str) -> int:
        return _index_of_buffer(tabs, buffer_id)

    def all_tab_widgets(self) -> list[QTabWidget]:
        """Every editor group's tab widget, first group first."""
        window = self._window
        groups = getattr(window, "_editor_groups", None)
        if groups is not None:
            return list(groups.tab_widgets())
        return [] if window._editor_tabs_widget is None else [window._editor_tabs_widget]

    def buffer_ids_in_tab_order(self) -> list[str]:
        """Buffer ids as the tabs show them, group by group, without repeats."""
        ordered: list[str] = []
        for tabs in self.all_tab_widgets():
            tab_bar = tabs.tabBar()
            for index in range(tabs.count()):
                data = tab_bar.tabData(index)
                buffer_id = data.get("buffer_id") if isinstance(data, dict) else None
                if isinstance(buffer_id, str) and buffer_id not in ordered:
                    ordered.append(buffer_id)
        return ordered

    def sync_open_order_from_tabs(self) -> None:
        """Make the editor manager's open order match the tabs after a move."""
        self._window._editor_manager.reorder_buffers(self.buffer_ids_in_tab_order())

    def refresh_tab_presentation(self, file_path: str) -> None:
        """Redraw every tab showing ``file_path``'s buffer, in every group."""
        tab_state = self._window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        for tabs in self.all_tab_widgets():
            index = _index_of_buffer(tabs, tab_state.buffer_id)
            if index >= 0:
                self.present_tab_at(index, tab_state, tabs=tabs)
        if self._window._editor_manager.active_tab() is tab_state:
            # The status bar repeats the active tab's disk state ("changed on disk").
            self._window._editor_tab_workflow.update_editor_status_for_path(tab_state.file_path)

    def present_tab_at(
        self,
        tab_index: int,
        tab_state: EditorTabState,
        *,
        tabs: QTabWidget | None = None,
    ) -> None:
        target = self._window._editor_tabs_widget if tabs is None else tabs
        if target is None:
            return
        data = tab_presentation_data(tab_state)
        tab_bar = target.tabBar()
        # Data first: the label's width depends on the markers it asks for.
        tab_bar.setTabData(tab_index, data)
        suffix = " *" if tab_state.is_dirty else ""
        target.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        target.setTabToolTip(
            tab_index,
            editor_tab_tooltip(
                tab_state.file_path,
                is_dirty=tab_state.is_dirty,
                is_preview=tab_state.is_preview,
                is_stale=bool(data["is_stale"]),
                is_missing=bool(data["is_missing"]),
            ),
        )
        page = target.widget(tab_index)
        if isinstance(page, EditorTabPage):
            page.info_bar.set_state(tab_disk_state(data), tab_state.file_path)
        tab_bar.update()

    def apply_tab_chrome_theme(self, tokens: Any) -> None:
        """Theme the tab markers, the info bars, and editors shown only as extra views."""
        primary_views = set(map(id, self._window._editor_widgets_by_path.values()))
        registered_panes = set(map(id, self._window._tab_content_registry.markdown_panes_by_path.values()))
        groups = getattr(self._window, "_editor_groups", None)
        if groups is not None:
            groups.apply_theme_colors(accent=tokens.accent)
        for tabs in self.all_tab_widgets():
            tab_bar = tabs.tabBar()
            if isinstance(tab_bar, MiddleClickTabBar):
                tab_bar.tab_style().set_marker_colors(
                    warning=tokens.diag_warning_color,
                    error=tokens.diag_error_color,
                    muted=tokens.text_muted,
                )
                tab_bar.update()
            for index in range(tabs.count()):
                page = tabs.widget(index)
                if not isinstance(page, EditorTabPage):
                    continue
                page.info_bar.apply_theme(tokens)
                content = page.content()
                if isinstance(content, CodeEditorWidget) and id(content) not in primary_views:
                    content.apply_theme(tokens)
                elif isinstance(content, MarkdownEditorPane) and id(content) not in registered_panes:
                    # A second group's markdown view; registered panes are themed with the rest.
                    content.apply_theme(tokens)

    def replace_tab_content_widget(self, file_path: str, new_widget: object) -> None:
        tab_state = self._window._editor_manager.get_tab(file_path)
        if tab_state is None or not isinstance(new_widget, QWidget):
            return
        for tabs in self.all_tab_widgets():
            index = _index_of_buffer(tabs, tab_state.buffer_id)
            page = tabs.widget(index) if index >= 0 else None
            if isinstance(page, EditorTabPage) and page.content() is not new_widget:
                if page.isAncestorOf(new_widget):
                    page.set_content(new_widget)
        self.refresh_tab_presentation(file_path)

    def promote_preview_tab(self, file_path: str) -> bool:
        window = self._window
        promoted_tab = window._editor_manager.promote_tab(file_path)
        if promoted_tab is None:
            return False
        if not promoted_tab.is_preview:
            window._editor_tab_workflow.refresh_tab_presentation(promoted_tab.file_path)
        return True

    def promote_existing_preview_tab(self) -> bool:
        window = self._window
        preview_tab = window._editor_manager.preview_tab()
        if preview_tab is None:
            return False
        return window._editor_tab_workflow.promote_preview_tab(preview_tab.file_path)

    def active_editor_widget(self) -> object | None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        if active_tab is None:
            return None
        return window._editor_widgets_by_path.get(active_tab.buffer_id)

    def advance_buffer_revision(self, file_path: str) -> int:
        return self._window._workspace_controller.advance_buffer_revision(file_path)

    def buffer_revision(self, file_path: str) -> int | None:
        return self._window._workspace_controller.buffer_revision(file_path)

    def handle_toggle_comment_action(self) -> None:
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.toggle_comment_selection()

    def handle_indent_action(self) -> None:
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.indent_selection()

    def handle_outdent_action(self) -> None:
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.outdent_selection()

    def handle_paste_reindented_flat_python_action(self) -> None:
        window = self._window
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(window, "Paste and Re-indent Flat Python", "Open a file tab first.")
            return
        result = editor_widget.paste_reindented_flat_python()
        window.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def handle_reindent_flat_python_selection_action(self) -> None:
        window = self._window
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(window, "Re-indent Flat Python Selection", "Open a file tab first.")
            return
        result = editor_widget.reindent_flat_python_selection()
        window.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def handle_paste_hint_repair_result(self, result: FlatPythonIndentRepairResult) -> None:
        """Surface flat-Python paste repair feedback in the status bar."""
        self._window.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def enable_auto_reindent_flat_python_paste_from_hint(self) -> None:
        """Persist auto-re-indent ON and propagate to open editors. Called by the paste hint's "Always" button."""
        window = self._window
        if window._editor_auto_reindent_flat_python_paste:
            return
        window._editor_auto_reindent_flat_python_paste = True
        try:
            window._settings_service.update_global(_enable_auto_reindent_flat_python_paste_in_payload)
        except Exception:
            window._logger.exception("Failed to persist auto-reindent flat-Python paste setting.")
        window._editor_tab_workflow.apply_editor_preferences_to_open_editors()

    def handle_set_language_mode_action(self) -> None:
        window = self._window
        editor_widget = self.active_editor_widget()
        active_tab = window._editor_manager.active_tab()
        if editor_widget is None or active_tab is None:
            QMessageBox.warning(window, "Language Mode", "Open a file tab first.")
            return
        mode_items = [("auto", "Auto Detect")]
        mode_items.extend(editor_widget.available_language_modes())
        labels = [label for _key, label in mode_items]
        current_key = editor_widget.language_override_key() or "auto"
        current_index = next((index for index, (key, _label) in enumerate(mode_items) if key == current_key), 0)
        selected_label, ok = QInputDialog.getItem(
            window,
            "Language Mode",
            "Use syntax mode:",
            labels,
            current_index,
            False,
        )
        if not ok:
            return
        selected_key = next((key for key, label in mode_items if label == selected_label), "auto")
        if selected_key == "auto":
            editor_widget.clear_language_override()
        else:
            editor_widget.set_language_override(selected_key)
        window._editor_tab_workflow.update_editor_status_for_path(active_tab.file_path)

    def handle_clear_language_override_action(self) -> None:
        window = self._window
        editor_widget = self.active_editor_widget()
        active_tab = window._editor_manager.active_tab()
        if editor_widget is None or active_tab is None:
            QMessageBox.warning(window, "Language Mode", "Open a file tab first.")
            return
        editor_widget.clear_language_override()
        window._editor_tab_workflow.update_editor_status_for_path(active_tab.file_path)

    def handle_inspect_token_action(self) -> None:
        window = self._window
        editor_widget = self.active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(window, "Token Inspector", "Open a file tab first.")
            return
        QMessageBox.information(window, "Token Inspector", editor_widget.describe_token_under_cursor())


def _enable_auto_reindent_flat_python_paste_in_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Settings-service updater that flips ``editor.auto_reindent_flat_python_paste`` on."""
    updated = dict(payload)
    editor_section_raw = updated.get(constants.UI_EDITOR_SETTINGS_KEY)
    editor_section: dict[str, Any] = (
        dict(editor_section_raw) if isinstance(editor_section_raw, dict) else {}
    )
    editor_section[constants.UI_EDITOR_AUTO_REINDENT_FLAT_PYTHON_PASTE_KEY] = True
    updated[constants.UI_EDITOR_SETTINGS_KEY] = editor_section
    return updated


def _flat_python_repair_status_message(result: FlatPythonIndentRepairResult) -> str:
    if result.reason == "not a flat Python paste":
        return "Inserted unchanged: not a flat Python paste."
    if result.reason == "no selection or recent paste":
        return "Select pasted Python lines before running re-indent."
    if result.changed and result.parse_ok:
        return "Re-indented flat Python paste."
    if result.changed:
        return f"Applied best-effort Python re-indent ({result.confidence} confidence)."
    return "Flat Python indentation did not need changes."
