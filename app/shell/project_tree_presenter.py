"""Project-tree presentation helpers for the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtWidgets import QApplication, QMenu, QTreeWidgetItem

from app.core.models import LoadedProject
from app.project.project_tree import build_project_tree
from app.project.project_tree_presenter import ProjectTreeDisplayNode, build_project_tree_display


class ProjectTreePresenter:
    """Builds and restores the visual project tree."""

    def __init__(
        self,
        window: Any,
        *,
        absolute_path_role: int,
        is_directory_role: int,
        relative_path_role: int,
    ) -> None:
        self._window = window
        self._absolute_path_role = absolute_path_role
        self._is_directory_role = is_directory_role
        self._relative_path_role = relative_path_role

    def populate(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        window = self._window
        if window._project_tree_widget is None:
            return

        expanded_paths: set[str] = set()
        selected_paths: set[str] = set()
        if preserve_state:
            expanded_paths, selected_paths = self.capture_state()
        window._project_tree_widget.clear()
        root_nodes = build_project_tree(loaded_project.entries)
        display_nodes = build_project_tree_display(root_nodes)
        for display_node in display_nodes:
            root_item = self.build_tree_item(display_node)
            window._project_tree_widget.addTopLevelItem(root_item)
            if not preserve_state and display_node.is_directory:
                root_item.setExpanded(True)
                root_item.setIcon(0, window._tree_folder_open_icon)
        if preserve_state:
            self.restore_state(expanded_paths=expanded_paths, selected_paths=selected_paths)

    def capture_state(self) -> tuple[set[str], set[str]]:
        window = self._window
        if window._project_tree_widget is None:
            return (set(), set())
        expanded_paths: set[str] = set()
        selected_paths: set[str] = set()
        for item in self.iter_items():
            relative_path = str(item.data(0, self._relative_path_role) or "")
            if not relative_path:
                continue
            if item.isExpanded():
                expanded_paths.add(relative_path)
            if item.isSelected():
                selected_paths.add(relative_path)
        return (expanded_paths, selected_paths)

    def restore_state(self, *, expanded_paths: set[str], selected_paths: set[str]) -> None:
        window = self._window
        if window._project_tree_widget is None:
            return
        for item in self.iter_items():
            relative_path = str(item.data(0, self._relative_path_role) or "")
            if not relative_path:
                continue
            if bool(item.data(0, self._is_directory_role)):
                item.setExpanded(relative_path in expanded_paths)
                item.setIcon(
                    0,
                    window._tree_folder_open_icon if item.isExpanded() else window._tree_folder_icon,
                )
            item.setSelected(relative_path in selected_paths)

    def iter_items(self) -> list[QTreeWidgetItem]:
        window = self._window
        if window._project_tree_widget is None:
            return []
        collected: list[QTreeWidgetItem] = []
        for index in range(window._project_tree_widget.topLevelItemCount()):
            root_item = window._project_tree_widget.topLevelItem(index)
            if root_item is None:
                continue
            collected.extend(self.collect_descendants(root_item))
        return collected

    def collect_descendants(self, root_item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        collected = [root_item]
        for child_index in range(root_item.childCount()):
            child_item = root_item.child(child_index)
            if child_item is None:
                continue
            collected.extend(self.collect_descendants(child_item))
        return collected

    def build_tree_item(self, node: ProjectTreeDisplayNode) -> QTreeWidgetItem:
        window = self._window
        item = QTreeWidgetItem([node.display_label])
        item.setData(0, self._absolute_path_role, node.absolute_path)
        item.setData(0, self._is_directory_role, node.is_directory)
        item.setData(0, self._relative_path_role, node.relative_path)
        if node.is_directory:
            item.setIcon(0, window._tree_folder_icon)
        else:
            filename = Path(node.absolute_path).name.lower()
            icon = window._tree_filename_icon_map.get(filename)
            if icon is None:
                ext = Path(node.absolute_path).suffix.lower()
                icon = window._tree_file_icon_map.get(ext, window._tree_file_icon)
            item.setIcon(0, icon)
            if (
                window._loaded_project is not None
                and node.relative_path == window._loaded_project.metadata.default_entry
            ):
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setIcon(0, window._tree_entrypoint_icon)

        for child_node in node.children:
            item.addChild(self.build_tree_item(child_node))
        return item

    def selected_paths(self) -> list[tuple[str, str, bool]]:
        window = self._window
        if window._project_tree_widget is None:
            return []
        entries: list[tuple[str, str, bool]] = []
        for item in window._project_tree_widget.selectedItems():
            abs_path = str(item.data(0, self._absolute_path_role) or "")
            rel_path = str(item.data(0, self._relative_path_role) or "")
            is_dir = bool(item.data(0, self._is_directory_role))
            if abs_path:
                entries.append((abs_path, rel_path, is_dir))
        return entries

    def item_entry(self, item: QTreeWidgetItem | None) -> tuple[str, str, bool] | None:
        if item is None:
            return None
        abs_path = str(item.data(0, self._absolute_path_role) or "")
        if not abs_path:
            return None
        rel_path = str(item.data(0, self._relative_path_role) or "")
        is_dir = bool(item.data(0, self._is_directory_role))
        return (abs_path, rel_path, is_dir)

    def show_context_menu(self, position: object) -> None:
        window = self._window
        if window._project_tree_widget is None:
            return
        item = window._project_tree_widget.itemAt(position)
        if item is None:
            return
        clicked_entry = self.item_entry(item)
        if clicked_entry is None:
            return
        if not item.isSelected():
            window._project_tree_widget.clearSelection()
            item.setSelected(True)
            window._project_tree_widget.setCurrentItem(item)
        selected = self.selected_paths()
        if not selected:
            return

        if len(selected) > 1:
            self.show_bulk_context_menu(position, selected)
        else:
            self.show_single_item_context_menu(position, clicked_entry)

    def show_single_item_context_menu(
        self,
        position: object,
        entry: tuple[str, str, bool],
    ) -> None:
        window = self._window
        assert window._project_tree_widget is not None
        absolute_path, relative_path, is_directory = entry

        menu = QMenu(window)
        new_file_action = menu.addAction("New File…")
        new_folder_action = menu.addAction("New Folder…")
        menu.addSeparator()
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Move to Trash")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Path")
        copy_relative_path_action = menu.addAction("Copy Relative Path")
        reveal_action = menu.addAction("Reveal in File Manager")
        local_history_action = None
        if not is_directory:
            local_history_action = menu.addAction("Local History...")
        run_file_action = None
        set_entry_point_action = None
        if (
            not is_directory
            and window._loaded_project is not None
            and Path(absolute_path).suffix.lower() == ".py"
        ):
            menu.addSeparator()
            run_file_action = menu.addAction("Run")
            assert run_file_action is not None
            run_file_action.setEnabled(not window._run_service.supervisor.is_running())
            set_entry_point_action = menu.addAction("Set as Entry Point")
            assert set_entry_point_action is not None
            if relative_path == window._loaded_project.metadata.default_entry:
                set_entry_point_action.setEnabled(False)

        assert paste_action is not None
        paste_action.setEnabled(len(window._tree_clipboard_paths) > 0)
        chosen = menu.exec_(window._project_tree_widget.viewport().mapToGlobal(position))
        if chosen is None:
            return

        if chosen == new_file_action:
            window._handle_tree_new_file(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == new_folder_action:
            window._handle_tree_new_folder(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == rename_action:
            window._handle_tree_rename(absolute_path)
        elif chosen == delete_action:
            window._handle_tree_delete(absolute_path)
        elif chosen == duplicate_action:
            window._handle_tree_duplicate(absolute_path)
        elif chosen == copy_action:
            window._tree_clipboard_paths = [absolute_path]
            window._tree_clipboard_cut = False
        elif chosen == cut_action:
            window._tree_clipboard_paths = [absolute_path]
            window._tree_clipboard_cut = True
        elif chosen == paste_action:
            window._handle_tree_paste(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == copy_path_action:
            QApplication.clipboard().setText(absolute_path)
        elif chosen == copy_relative_path_action:
            QApplication.clipboard().setText(relative_path)
        elif chosen == reveal_action:
            window._reveal_path_in_file_manager(absolute_path)
        elif not is_directory and local_history_action is not None and chosen == local_history_action:
            window._local_history_workflow.show_local_history_for_path(absolute_path)
        elif run_file_action is not None and chosen == run_file_action:
            window._handle_tree_run_file(absolute_path)
        elif set_entry_point_action is not None and chosen == set_entry_point_action:
            window._set_project_entry_point(relative_path)

    def show_bulk_context_menu(
        self,
        position: object,
        selected: list[tuple[str, str, bool]],
    ) -> None:
        window = self._window
        assert window._project_tree_widget is not None
        abs_paths = [entry[0] for entry in selected]

        menu = QMenu(window)
        delete_action = menu.addAction(f"Move {len(selected)} Items to Trash")
        duplicate_action = menu.addAction(f"Duplicate {len(selected)} Items")
        menu.addSeparator()
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Paths")
        copy_relative_path_action = menu.addAction("Copy Relative Paths")

        assert paste_action is not None
        paste_action.setEnabled(len(window._tree_clipboard_paths) > 0)
        chosen = menu.exec_(window._project_tree_widget.viewport().mapToGlobal(position))
        if chosen is None:
            return

        if chosen == delete_action:
            window._handle_tree_bulk_delete(abs_paths)
        elif chosen == duplicate_action:
            window._handle_tree_bulk_duplicate(abs_paths)
        elif chosen == copy_action:
            window._tree_clipboard_paths = list(abs_paths)
            window._tree_clipboard_cut = False
        elif chosen == cut_action:
            window._tree_clipboard_paths = list(abs_paths)
            window._tree_clipboard_cut = True
        elif chosen == paste_action:
            first_abs, _, first_is_dir = selected[0]
            dest = first_abs if first_is_dir else str(Path(first_abs).parent)
            window._handle_tree_paste(dest)
        elif chosen == copy_path_action:
            QApplication.clipboard().setText("\n".join(abs_paths))
        elif chosen == copy_relative_path_action:
            rel_paths = [entry[1] for entry in selected]
            QApplication.clipboard().setText("\n".join(rel_paths))
