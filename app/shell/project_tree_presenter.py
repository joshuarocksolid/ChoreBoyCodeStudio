"""Project-tree presentation helpers for the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QAbstractItemView, QApplication, QMenu, QTreeWidgetItem

from app.core.models import LoadedProject
from app.project.project_tree import build_project_tree
from app.project.project_tree_presenter import ProjectTreeDisplayNode, build_project_tree_display
from app.shell.session_persistence import SessionTreeState
from app.shell.tree_item_roles import (
    TREE_ROLE_ABSOLUTE_PATH,
    TREE_ROLE_IS_DIRECTORY,
    TREE_ROLE_LAZY_UNLOADED,
    TREE_ROLE_RELATIVE_PATH,
)


class ProjectTreePresenter:
    """Builds and restores the visual project tree."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._display_node_by_relative_path: dict[str, ProjectTreeDisplayNode] = {}
        self._item_by_relative_path: dict[str, QTreeWidgetItem] = {}
        self._reveal_suppressed = False

    def set_reveal_suppressed(self, suppressed: bool) -> None:
        """When True, :meth:`reveal_path` is a no-op (e.g. during session restore)."""
        self._reveal_suppressed = suppressed

    def populate(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        window = self._window
        if window._project_tree_widget is None:
            return

        saved_state = self.capture_view_state() if preserve_state else None
        window._project_tree_widget.clear()
        self._display_node_by_relative_path.clear()
        self._item_by_relative_path.clear()

        root_nodes = build_project_tree(loaded_project.entries)
        display_nodes = build_project_tree_display(
            root_nodes,
            source_roots=tuple(loaded_project.metadata.source_roots),
        )
        self._index_display_nodes(display_nodes)
        for display_node in display_nodes:
            root_item = self.build_tree_item(display_node, lazy=True)
            window._project_tree_widget.addTopLevelItem(root_item)
        if saved_state is not None:
            self.restore_view_state(saved_state)

    def handle_item_expanded(self, item: QTreeWidgetItem) -> None:
        self.ensure_children_loaded(item)

    def ensure_children_loaded(self, item: QTreeWidgetItem) -> None:
        if not bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            return
        if not bool(item.data(0, TREE_ROLE_LAZY_UNLOADED)):
            return
        relative_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
        display_node = self._display_node_by_relative_path.get(relative_path)
        if display_node is None:
            return
        item.takeChildren()
        item.setData(0, TREE_ROLE_LAZY_UNLOADED, False)
        for child_node in display_node.children:
            item.addChild(self.build_tree_item(child_node, lazy=True))

    def capture_view_state(self) -> SessionTreeState:
        window = self._window
        tree = window._project_tree_widget
        if tree is None:
            return SessionTreeState()
        expanded_paths: set[str] = set()
        selected_paths: set[str] = set()
        for item in self.iter_items():
            relative_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
            if not relative_path:
                continue
            if item.isExpanded():
                expanded_paths.add(relative_path)
            if item.isSelected():
                selected_paths.add(relative_path)
        return SessionTreeState(
            expanded_paths=tuple(sorted(expanded_paths)),
            selected_paths=tuple(sorted(selected_paths)),
            vertical_scroll=tree.verticalScrollBar().value(),
            horizontal_scroll=tree.horizontalScrollBar().value(),
        )

    def restore_view_state(self, tree_state: SessionTreeState) -> None:
        expanded_paths = set(tree_state.expanded_paths)
        selected_paths = set(tree_state.selected_paths)
        self._restore_expansion_and_selection(
            expanded_paths=expanded_paths,
            selected_paths=selected_paths,
        )
        self._restore_scroll_position(tree_state.vertical_scroll, tree_state.horizontal_scroll)

    def capture_full_state(self) -> SessionTreeState:
        """Backward-compatible alias for session persistence."""
        return self.capture_view_state()

    def restore_full_state(self, tree_state: SessionTreeState) -> None:
        """Backward-compatible alias for session persistence."""
        self.restore_view_state(tree_state)

    def _restore_scroll_position(self, vertical: int, horizontal: int) -> None:
        window = self._window
        tree = window._project_tree_widget
        if tree is None:
            return

        def _apply_scroll() -> None:
            current_tree = window._project_tree_widget
            if current_tree is None:
                return
            current_tree.verticalScrollBar().setValue(vertical)
            current_tree.horizontalScrollBar().setValue(horizontal)

        QTimer.singleShot(0, _apply_scroll)

    def _restore_expansion_and_selection(
        self,
        *,
        expanded_paths: set[str],
        selected_paths: set[str],
    ) -> None:
        if self._window._project_tree_widget is None:
            return
        paths_to_materialize = set(expanded_paths) | set(selected_paths)
        for relative_path in sorted(paths_to_materialize, key=lambda path: path.count("/")):
            self._materialize_path(relative_path)
        for relative_path in paths_to_materialize:
            item = self._find_item_by_relative_path(relative_path)
            if item is None:
                continue
            if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
                expanded = relative_path in expanded_paths
                item.setExpanded(expanded)
                self.set_folder_icon(item, expanded=expanded)
            item.setSelected(relative_path in selected_paths)

    def set_folder_icon(self, item: QTreeWidgetItem, *, expanded: bool) -> None:
        window = self._window
        if expanded:
            item.setIcon(0, window._tree_folder_open_icon)
        else:
            item.setIcon(0, window._tree_folder_icon)

    def reveal_path(self, file_path: str) -> None:
        """Select and scroll to the tree item matching ``file_path``."""
        if self._reveal_suppressed:
            return
        window = self._window
        tree = window._project_tree_widget
        if tree is None or not file_path:
            return
        try:
            target = str(Path(file_path).expanduser().resolve())
        except OSError:
            return
        for item in self.iter_items():
            raw = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
            if not raw:
                continue
            try:
                candidate = str(Path(raw).expanduser().resolve())
            except OSError:
                continue
            if candidate != target:
                continue
            parent = item.parent()
            while parent is not None:
                self.ensure_children_loaded(parent)
                if not parent.isExpanded():
                    parent.setExpanded(True)
                    if bool(parent.data(0, TREE_ROLE_IS_DIRECTORY)):
                        self.set_folder_icon(parent, expanded=True)
                parent = parent.parent()
            tree.clearSelection()
            tree.setCurrentItem(item)
            item.setSelected(True)
            tree.scrollToItem(item, QAbstractItemView.PositionAtCenter)
            return

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

    def build_tree_item(self, node: ProjectTreeDisplayNode, *, lazy: bool = False) -> QTreeWidgetItem:
        window = self._window
        item = QTreeWidgetItem([node.display_label])
        item.setData(0, TREE_ROLE_ABSOLUTE_PATH, node.absolute_path)
        item.setData(0, TREE_ROLE_IS_DIRECTORY, node.is_directory)
        item.setData(0, TREE_ROLE_RELATIVE_PATH, node.relative_path)
        item.setData(0, TREE_ROLE_LAZY_UNLOADED, False)
        self._item_by_relative_path[node.relative_path] = item
        if node.is_directory:
            item.setIcon(0, window._tree_folder_icon)
            if node.children:
                if lazy:
                    item.addChild(QTreeWidgetItem([""]))
                    item.setData(0, TREE_ROLE_LAZY_UNLOADED, True)
                else:
                    for child_node in node.children:
                        item.addChild(self.build_tree_item(child_node, lazy=False))
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
        return item

    def selected_paths(self) -> list[tuple[str, str, bool]]:
        window = self._window
        if window._project_tree_widget is None:
            return []
        entries: list[tuple[str, str, bool]] = []
        for item in window._project_tree_widget.selectedItems():
            abs_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
            rel_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
            is_dir = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
            if abs_path:
                entries.append((abs_path, rel_path, is_dir))
        return entries

    def item_entry(self, item: QTreeWidgetItem | None) -> tuple[str, str, bool] | None:
        if item is None:
            return None
        abs_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
        if not abs_path:
            return None
        rel_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
        is_dir = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
        return (abs_path, rel_path, is_dir)

    def selected_destination_directory(self) -> str | None:
        """Return the directory path for the current tree selection, or the project root."""
        window = self._window
        if window._loaded_project is None:
            return None
        if window._project_tree_widget is None:
            return window._loaded_project.project_root
        current = window._project_tree_widget.currentItem()
        if current is None:
            return window._loaded_project.project_root
        entry = self.item_entry(current)
        if entry is None:
            return window._loaded_project.project_root
        absolute_path, _, is_directory = entry
        return absolute_path if is_directory else str(Path(absolute_path).parent)

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
        mark_source_root_action = None
        unmark_source_root_action = None
        if is_directory and window._loaded_project is not None:
            configured_roots = set(window._loaded_project.metadata.source_roots)
            normalized_relative = relative_path.replace("\\", "/").strip("/")
            menu.addSeparator()
            if normalized_relative in configured_roots:
                unmark_source_root_action = menu.addAction("Unmark Sources Root")
            else:
                mark_source_root_action = menu.addAction("Mark as Sources Root")
        local_history_action = None
        if not is_directory:
            local_history_action = menu.addAction("Local History...")
        run_file_action = None
        run_file_with_args_action = None
        set_entry_point_action = None
        if (
            not is_directory
            and window._loaded_project is not None
            and Path(absolute_path).suffix.lower() == ".py"
        ):
            menu.addSeparator()
            run_file_action = menu.addAction("Run")
            assert run_file_action is not None
            run_is_idle = not window._run_service.supervisor.is_running()
            run_file_action.setEnabled(run_is_idle)
            run_file_with_args_action = menu.addAction("Run With Arguments...")
            assert run_file_with_args_action is not None
            run_file_with_args_action.setEnabled(run_is_idle)
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
            window._run_launch_workflow.handle_tree_run_file(absolute_path)
        elif run_file_with_args_action is not None and chosen == run_file_with_args_action:
            window._run_launch_workflow.handle_tree_run_file_with_arguments(absolute_path)
        elif set_entry_point_action is not None and chosen == set_entry_point_action:
            window._set_project_entry_point(relative_path)
        elif mark_source_root_action is not None and chosen == mark_source_root_action:
            window._handle_tree_mark_source_root(relative_path)
        elif unmark_source_root_action is not None and chosen == unmark_source_root_action:
            window._handle_tree_unmark_source_root(relative_path)

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

    def _index_display_nodes(self, nodes: list[ProjectTreeDisplayNode]) -> None:
        for node in nodes:
            self._display_node_by_relative_path[node.relative_path] = node
            if node.children:
                self._index_display_nodes(node.children)

    def _materialize_path(self, relative_path: str) -> None:
        if not relative_path:
            return
        parts = relative_path.split("/")
        for depth in range(len(parts)):
            partial = "/".join(parts[: depth + 1])
            item = self._find_item_by_relative_path(partial)
            if item is None:
                continue
            self.ensure_children_loaded(item)

    def _find_item_by_relative_path(self, relative_path: str) -> QTreeWidgetItem | None:
        return self._item_by_relative_path.get(relative_path)
