"""Editor-tab presentation and state coordination helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtWidgets import QInputDialog, QMessageBox, QTabBar

from app.core import constants
from app.editors.text_editing import FlatPythonIndentRepairResult


class EditorTabsCoordinator:
    """Keeps editor-manager tab state and Qt tab chrome in sync."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def tab_index_for_path(self, file_path: str) -> int:
        window = self._window
        if window._editor_tabs_widget is None:
            return -1

        normalized_path = str(Path(file_path).expanduser().resolve())
        for index in range(window._editor_tabs_widget.count()):
            if window._editor_tabs_widget.tabToolTip(index) == normalized_path:
                return index
        return -1

    def refresh_tab_presentation(self, file_path: str) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        tab_state = window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        tab_index = window._editor_tab_workflow.tab_index_for_path(file_path)
        if tab_index < 0:
            return
        suffix = " *" if tab_state.is_dirty else ""
        window._editor_tabs_widget.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        tab_bar = window._editor_tabs_widget.tabBar()
        if isinstance(tab_bar, QTabBar):
            tab_bar.setTabData(
                tab_index,
                {"is_preview": tab_state.is_preview, "file_path": tab_state.file_path},
            )
            tab_bar.update()

    def replace_tab_content_widget(self, file_path: str, new_widget: object) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        tab_index = self.tab_index_for_path(file_path)
        if tab_index < 0:
            return
        tabs = window._editor_tabs_widget
        label = tabs.tabText(tab_index)
        tooltip = tabs.tabToolTip(tab_index)
        tabs.removeTab(tab_index)
        tabs.insertTab(tab_index, new_widget, label)
        tabs.setTabToolTip(tab_index, tooltip)
        tabs.setCurrentIndex(tab_index)
        tab_bar = tabs.tabBar()
        if isinstance(tab_bar, QTabBar):
            tab_bar.update()
        window = self._window
        if hasattr(window, "_editor_tab_workflow"):
            window._editor_tab_workflow.refresh_tab_presentation(file_path)

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
        return window._editor_widgets_by_path.get(active_tab.file_path)

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
