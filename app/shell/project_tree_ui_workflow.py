"""Project tree UI handlers for the main shell window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from PySide2.QtCore import QTimer, QUrl
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QStackedWidget, QTabWidget, QTreeWidgetItem

from app.core.errors import ProjectManifestValidationError
from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.markdown_rendering import is_markdown_path
from app.project.file_operation_models import ImportUpdatePolicy
from app.project.project_manifest import set_project_default_entry
from app.shell.tree_item_roles import TREE_ROLE_IS_DIRECTORY


class ProjectTreeUiWorkflowHost(Protocol):
    """Host ports for :class:`ProjectTreeUiWorkflow`."""

    def parent_widget(self) -> Any:
        ...

    def sidebar_stack(self) -> QStackedWidget | None:
        ...

    def search_sidebar(self) -> Any | None:
        ...

    def explorer_new_file_btn(self) -> Any | None:
        ...

    def explorer_new_folder_btn(self) -> Any | None:
        ...

    def explorer_refresh_btn(self) -> Any | None:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def set_loaded_project(self, project: LoadedProject) -> None:
        ...

    def project_tree_presenter(self) -> Any:
        ...

    def editor_enable_preview(self) -> bool:
        ...

    def pending_project_tree_preview_path(self) -> str | None:
        ...

    def set_pending_project_tree_preview_path(self, path: str | None) -> None:
        ...

    def project_tree_preview_click_timer(self) -> QTimer:
        ...

    def editor_tab_factory(self) -> Any:
        ...

    def show_editor_screen(self) -> None:
        ...

    def project_tree_action_coordinator(self) -> Any:
        ...

    def project_tree_action_workflow(self) -> Any:
        ...

    def project_tree_controller(self) -> Any:
        ...

    def tree_clipboard_paths(self) -> list[str]:
        ...

    def set_tree_clipboard_paths(self, paths: list[str]) -> None:
        ...

    def tree_clipboard_cut(self) -> bool:
        ...

    def set_tree_clipboard_cut(self, cut: bool) -> None:
        ...

    def editor_tabs_widget(self) -> QTabWidget | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        ...

    def markdown_panes_by_path(self) -> dict[str, Any]:
        ...

    def debug_execution_editor(self) -> CodeEditorWidget | None:
        ...

    def clear_debug_execution_indicator(self) -> None:
        ...

    def refresh_tab_presentation(self, file_path: str) -> None:
        ...

    def open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        ...

    def import_update_policy(self) -> ImportUpdatePolicy:
        ...

    def save_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        ...

    def local_history_workflow(self) -> Any:
        ...

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        ...

    def project_rescan_workflow(self) -> Any:
        ...

    def source_root_workflow(self) -> Any:
        ...


class ProjectTreeUiWorkflow:
    """Owns project-tree sidebar interactions, context actions, and path updates."""

    def __init__(self, host: ProjectTreeUiWorkflowHost) -> None:
        self._host = host

    def handle_sidebar_view_changed(self, view_id: str) -> None:
        sidebar_stack = self._host.sidebar_stack()
        if sidebar_stack is None:
            return
        if view_id == "explorer":
            sidebar_stack.setCurrentIndex(0)
        elif view_id == "search":
            sidebar_stack.setCurrentIndex(1)
            search_sidebar = self._host.search_sidebar()
            if search_sidebar is not None:
                search_sidebar.focus_search()
        elif view_id == "test_explorer":
            sidebar_stack.setCurrentIndex(2)

    def handle_search_open_file_at_line(self, file_path: str, line_number: int) -> None:
        self._host.open_file_at_line(file_path, line_number, preview=False)

    def handle_search_preview_file_at_line(self, file_path: str, line_number: int) -> None:
        self._host.open_file_at_line(file_path, line_number, preview=True)

    def update_explorer_buttons_enabled(self) -> None:
        has_project = self._host.loaded_project() is not None
        new_file_btn = self._host.explorer_new_file_btn()
        if new_file_btn is not None:
            new_file_btn.setEnabled(has_project)
        new_folder_btn = self._host.explorer_new_folder_btn()
        if new_folder_btn is not None:
            new_folder_btn.setEnabled(has_project)
        refresh_btn = self._host.explorer_refresh_btn()
        if refresh_btn is not None:
            refresh_btn.setEnabled(has_project)

    def selected_tree_directory(self) -> str | None:
        """Return the directory path for the selected tree item, or the project root."""
        return self._host.project_tree_presenter().selected_destination_directory()

    def handle_explorer_new_file(self) -> None:
        target = self.selected_tree_directory()
        if target is not None:
            self.handle_tree_new_file(target)

    def handle_explorer_new_folder(self) -> None:
        target = self.selected_tree_directory()
        if target is not None:
            self.handle_tree_new_folder(target)

    def handle_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        presenter = self._host.project_tree_presenter()
        presenter.handle_item_expanded(item)
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            presenter.set_folder_icon(item, expanded=True)

    def handle_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            self._host.project_tree_presenter().set_folder_icon(item, expanded=False)

    def populate_project_tree(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        self._host.project_tree_presenter().populate(loaded_project, preserve_state=preserve_state)

    def iter_project_tree_items(self) -> list[QTreeWidgetItem]:
        return self._host.project_tree_presenter().iter_items()

    def handle_project_tree_item_click(self, item: QTreeWidgetItem, _column: int) -> None:
        entry = self._host.project_tree_presenter().item_entry(item)
        if entry is None:
            return
        _, _, is_directory = entry
        if is_directory:
            return
        absolute_path = entry[0]
        if not self._host.editor_enable_preview():
            self.cancel_pending_project_tree_preview()
            self._host.editor_tab_factory().open_file_in_editor(absolute_path, preview=False)
            return
        self._host.set_pending_project_tree_preview_path(absolute_path)
        self._host.project_tree_preview_click_timer().start()

    def open_pending_project_tree_preview(self) -> None:
        preview_path = self._host.pending_project_tree_preview_path()
        self._host.set_pending_project_tree_preview_path(None)
        if not preview_path:
            return
        self._host.editor_tab_factory().open_file_in_editor(preview_path, preview=True)

    def cancel_pending_project_tree_preview(self) -> None:
        self._host.set_pending_project_tree_preview_path(None)
        timer = self._host.project_tree_preview_click_timer()
        if timer.isActive():
            timer.stop()

    def handle_project_tree_item_activation(self, item: QTreeWidgetItem, _column: int) -> None:
        self.cancel_pending_project_tree_preview()
        entry = self._host.project_tree_presenter().item_entry(item)
        if entry is None:
            return
        absolute_path, _, is_directory = entry
        if is_directory or not absolute_path:
            return
        self._host.editor_tab_factory().open_file_in_editor(absolute_path, preview=False)

    def get_selected_tree_paths(self) -> list[tuple[str, str, bool]]:
        """Return (absolute_path, relative_path, is_directory) for each selected tree item."""
        return self._host.project_tree_presenter().selected_paths()

    def show_project_tree_context_menu(self, position: object) -> None:
        self._host.project_tree_presenter().show_context_menu(position)

    def handle_tree_new_file(self, destination_directory: str) -> None:
        parent = self._host.parent_widget()
        file_name, ok = QInputDialog.getText(parent, "New File", "File name:", QLineEdit.Normal, "")
        if not ok or not file_name.strip():
            return
        outcome = self._host.project_tree_action_coordinator().handle_new_file(
            destination_directory,
            file_name.strip(),
        )
        if outcome.error_message is not None:
            QMessageBox.warning(parent, "New File", outcome.error_message)
            return
        if outcome.created_path is not None:
            self._host.editor_tab_factory().open_file_in_editor(outcome.created_path, preview=False)
            self._host.show_editor_screen()

    def handle_tree_new_folder(self, destination_directory: str) -> None:
        parent = self._host.parent_widget()
        folder_name, ok = QInputDialog.getText(parent, "New Folder", "Folder name:", QLineEdit.Normal, "")
        if not ok or not folder_name.strip():
            return
        error_message = self._host.project_tree_action_coordinator().handle_new_folder(
            destination_directory,
            folder_name.strip(),
        )
        if error_message is not None:
            QMessageBox.warning(parent, "New Folder", error_message)

    def handle_tree_rename(self, source_path: str) -> None:
        parent = self._host.parent_widget()
        source = Path(source_path)
        new_name, ok = QInputDialog.getText(parent, "Rename", "New name:", QLineEdit.Normal, source.name)
        if not ok or not new_name.strip() or new_name.strip() == source.name:
            return
        error_message = self._host.project_tree_action_coordinator().handle_rename(source_path, new_name.strip())
        if error_message is not None:
            QMessageBox.warning(parent, "Rename", error_message)

    def handle_project_tree_delete_key(self) -> None:
        selected = self.get_selected_tree_paths()
        if not selected:
            return
        if len(selected) == 1:
            self.handle_tree_delete(selected[0][0])
        else:
            self.handle_tree_bulk_delete([entry[0] for entry in selected])

    def handle_project_tree_rename_key(self) -> None:
        selected = self.get_selected_tree_paths()
        if len(selected) != 1:
            return
        self.handle_tree_rename(selected[0][0])

    def handle_project_tree_copy_key(self) -> None:
        selected = self.get_selected_tree_paths()
        if not selected:
            return
        self._host.set_tree_clipboard_paths([entry[0] for entry in selected])
        self._host.set_tree_clipboard_cut(False)

    def handle_project_tree_cut_key(self) -> None:
        selected = self.get_selected_tree_paths()
        if not selected:
            return
        self._host.set_tree_clipboard_paths([entry[0] for entry in selected])
        self._host.set_tree_clipboard_cut(True)

    def handle_project_tree_paste_key(self) -> None:
        if not self._host.tree_clipboard_paths():
            return
        destination = self.selected_tree_directory()
        if destination is None:
            return
        self.handle_tree_paste(destination)

    def handle_tree_delete(self, target_path: str) -> None:
        self._host.project_tree_action_workflow().delete_paths(target_path)

    def handle_tree_duplicate(self, source_path: str) -> None:
        parent = self._host.parent_widget()
        error_message = self._host.project_tree_action_coordinator().handle_duplicate(source_path)
        if error_message is not None:
            QMessageBox.warning(parent, "Duplicate", error_message)

    def handle_tree_bulk_delete(self, paths: list[str]) -> None:
        self._host.project_tree_action_workflow().bulk_delete(paths)

    def handle_tree_bulk_duplicate(self, paths: list[str]) -> None:
        parent = self._host.parent_widget()
        failed = self._host.project_tree_action_coordinator().handle_bulk_duplicate(paths)
        if failed:
            QMessageBox.warning(parent, "Duplicate", "\n".join(failed))

    def handle_tree_paste(self, destination_directory: str) -> None:
        parent = self._host.parent_widget()
        failed, next_paths, next_cut = self._host.project_tree_action_coordinator().handle_paste(
            destination_directory=destination_directory,
            clipboard_paths=self._host.tree_clipboard_paths(),
            clipboard_cut=self._host.tree_clipboard_cut(),
        )
        self._host.set_tree_clipboard_paths(next_paths)
        self._host.set_tree_clipboard_cut(next_cut)
        if failed:
            QMessageBox.warning(parent, "Paste", "\n".join(failed))

    def handle_project_tree_drop(self, source_path: str, target_path: str) -> bool:
        parent = self._host.parent_widget()
        error_message = self._host.project_tree_action_coordinator().handle_drop_move(source_path, target_path)
        if error_message is not None:
            QMessageBox.warning(parent, "Move", error_message)
            return False
        return True

    def reveal_path_in_file_manager(self, path: str) -> None:
        target = Path(path).expanduser().resolve()
        reveal_target = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(reveal_target)))

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

    def close_deleted_editor_paths(self, deleted_path: str) -> None:
        self._host.project_tree_action_coordinator().close_deleted_editor_paths(deleted_path)

    def apply_path_move_updates(self, source_path: str, destination_path: str) -> None:
        self._host.project_tree_action_coordinator().apply_path_move_updates(source_path, destination_path)

    def update_widget_language_for_path(self, widget: CodeEditorWidget, new_path: str) -> None:
        widget.set_language_for_path(new_path)
        markdown_panes = self._host.markdown_panes_by_path()
        for old_path, markdown_pane in list(markdown_panes.items()):
            if markdown_pane.source_editor() is widget:
                markdown_panes.pop(old_path, None)
                if is_markdown_path(new_path):
                    markdown_pane.set_file_path(new_path)
                    markdown_panes[new_path] = markdown_pane
                break

    def update_tab_path_and_name(self, tab_index: int, new_path: str) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return
        editor_tabs_widget.setTabToolTip(tab_index, new_path)
        self._host.refresh_tab_presentation(new_path)

    def maybe_rewrite_imports_for_move(self, source_path: str, destination_path: str) -> None:
        loaded_project = self._host.loaded_project()
        self._host.project_tree_controller().maybe_rewrite_imports_for_move(
            project_root=None if loaded_project is None else loaded_project.project_root,
            source_path=source_path,
            destination_path=destination_path,
            resolve_policy_for_operation=self.resolve_import_update_policy_for_operation,
            request_confirmation=self.request_import_rewrite_confirmation,
            show_warning=lambda details: self.show_import_update_warning(details),
            on_applied=self.handle_import_rewrites_applied,
        )

    def handle_import_rewrites_applied(self, previews: Any) -> None:
        payloads = {preview.file_path: preview.updated_content for preview in previews}
        self._host.local_history_workflow().record_transaction(
            payloads,
            source="import_rewrite",
            label="Update imports after move/rename",
        )
        self._host.refresh_open_tabs_from_disk(sorted(payloads.keys()))

    def request_import_rewrite_confirmation(self, message: str) -> bool:
        parent = self._host.parent_widget()
        answer = QMessageBox.question(
            parent,
            "Update imports?",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return answer == QMessageBox.Yes

    def show_import_update_warning(self, details: str) -> None:
        QMessageBox.warning(self._host.parent_widget(), "Import update failed", details)

    def resolve_import_update_policy_for_operation(self) -> ImportUpdatePolicy:
        if self._host.import_update_policy() != ImportUpdatePolicy.ASK:
            return self._host.import_update_policy()

        parent = self._host.parent_widget()
        labels = [
            ("Ask every time (this operation only)", ImportUpdatePolicy.ASK),
            ("Always update imports", ImportUpdatePolicy.ALWAYS),
            ("Never update imports", ImportUpdatePolicy.NEVER),
        ]
        selected_label, ok = QInputDialog.getItem(
            parent,
            "Import Update Policy",
            "Choose import update behavior:",
            [label for label, _ in labels],
            0,
            editable=False,
        )
        if not ok:
            return ImportUpdatePolicy.NEVER
        selected_policy = next(policy for label, policy in labels if label == selected_label)
        if selected_policy in {ImportUpdatePolicy.ALWAYS, ImportUpdatePolicy.NEVER}:
            persist = QMessageBox.question(
                parent,
                "Remember preference?",
                "Use this choice as default for future moves/renames?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if persist == QMessageBox.Yes:
                self._host.save_import_update_policy(selected_policy)
        return selected_policy

    def refresh_project_tree_from_disk(self) -> None:
        self._host.project_rescan_workflow().rescan_from_disk()

    def reload_current_project(self) -> None:
        self._host.project_rescan_workflow().rescan_from_disk(reload_plugins=True, reindex=True)

    def handle_tree_mark_source_root(self, relative_path: str) -> None:
        self._host.source_root_workflow().mark_source_root(relative_path)

    def handle_tree_unmark_source_root(self, relative_path: str) -> None:
        self._host.source_root_workflow().unmark_source_root(relative_path)

    def maybe_prompt_import_source_roots(self) -> None:
        self._host.source_root_workflow().maybe_prompt_import_source_roots()

    def set_project_entry_point(self, relative_path: str) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return False
        normalized_relative = relative_path.strip()
        if not normalized_relative:
            return False
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        entry_path = (project_root / normalized_relative).resolve()
        parent = self._host.parent_widget()
        if not entry_path.exists() or not entry_path.is_file():
            QMessageBox.warning(parent, "Entry point", "Selected entry file does not exist.")
            return False
        if entry_path.suffix.lower() != ".py":
            QMessageBox.warning(parent, "Entry point", "Entry point must reference a Python file.")
            return False
        try:
            entry_path.relative_to(project_root)
        except ValueError:
            QMessageBox.warning(parent, "Entry point", "Entry point must be inside the opened project.")
            return False

        try:
            updated_metadata = set_project_default_entry(
                loaded_project.manifest_path,
                default_entry=normalized_relative,
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(parent, "Entry point", str(exc))
            return False
        updated_project = replace(
            loaded_project,
            metadata=updated_metadata,
            manifest_materialized=True,
        )
        self._host.set_loaded_project(updated_project)
        self.populate_project_tree(updated_project, preserve_state=True)
        return True


class MainWindowProjectTreeUiHost:
    """Host ports for ``ProjectTreeUiWorkflow`` backed by a ``MainWindow`` instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def parent_widget(self) -> Any:
        return self._window

    def sidebar_stack(self) -> QStackedWidget | None:
        return self._window._sidebar_stack

    def search_sidebar(self) -> Any | None:
        return self._window._search_sidebar

    def explorer_new_file_btn(self) -> Any | None:
        return self._window._explorer_new_file_btn

    def explorer_new_folder_btn(self) -> Any | None:
        return self._window._explorer_new_folder_btn

    def explorer_refresh_btn(self) -> Any | None:
        return self._window._explorer_refresh_btn

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._window._loaded_project = project

    def project_tree_presenter(self) -> Any:
        return self._window._project_tree_presenter

    def editor_enable_preview(self) -> bool:
        return self._window._editor_enable_preview

    def pending_project_tree_preview_path(self) -> str | None:
        return self._window._pending_project_tree_preview_path

    def set_pending_project_tree_preview_path(self, path: str | None) -> None:
        self._window._pending_project_tree_preview_path = path

    def project_tree_preview_click_timer(self) -> QTimer:
        return self._window._project_tree_preview_click_timer

    def editor_tab_factory(self) -> Any:
        return self._window._editor_tab_factory

    def show_editor_screen(self) -> None:
        self._window._runtime_onboarding_workflow.show_editor_screen()

    def project_tree_action_coordinator(self) -> Any:
        return self._window._project_tree_action_coordinator

    def project_tree_action_workflow(self) -> Any:
        return self._window._project_tree_action_workflow

    def project_tree_controller(self) -> Any:
        return self._window._project_tree_controller

    def tree_clipboard_paths(self) -> list[str]:
        return self._window._tree_clipboard_paths

    def set_tree_clipboard_paths(self, paths: list[str]) -> None:
        self._window._tree_clipboard_paths = paths

    def tree_clipboard_cut(self) -> bool:
        return self._window._tree_clipboard_cut

    def set_tree_clipboard_cut(self, cut: bool) -> None:
        self._window._tree_clipboard_cut = cut

    def editor_tabs_widget(self) -> QTabWidget | None:
        return self._window._editor_tabs_widget

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        return self._window._editor_widgets_by_path

    def markdown_panes_by_path(self) -> dict[str, Any]:
        return self._window._markdown_panes_by_path

    def debug_execution_editor(self) -> CodeEditorWidget | None:
        return self._window._debug_execution_editor

    def clear_debug_execution_indicator(self) -> None:
        self._window._debug_inspector_workflow.clear_debug_execution_indicator()

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._window._editor_tab_workflow.refresh_tab_presentation(file_path)

    def open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        self._window._editor_tab_workflow.open_file_at_line(file_path, line_number, preview=preview)

    def import_update_policy(self) -> ImportUpdatePolicy:
        return self._window._import_update_policy

    def save_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        self._window._shell_preferences_runtime.save_import_update_policy(policy)

    def local_history_workflow(self) -> Any:
        return self._window._local_history_workflow

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._window._refresh_open_tabs_from_disk(file_paths)

    def project_rescan_workflow(self) -> Any:
        return self._window._project_rescan_workflow

    def source_root_workflow(self) -> Any:
        return self._window._source_root_workflow


def build_project_tree_ui_workflow(window: Any) -> ProjectTreeUiWorkflow:
    """Construct :class:`ProjectTreeUiWorkflow` for a ``MainWindow`` instance."""
    return ProjectTreeUiWorkflow(MainWindowProjectTreeUiHost(window))
