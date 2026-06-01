"""Project-tree context menu construction and dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtWidgets import QApplication, QMenu


def show_single_item_tree_context_menu(
    window: Any,
    position: object,
    entry: tuple[str, str, bool],
) -> None:
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


def show_bulk_tree_context_menu(
    window: Any,
    position: object,
    selected: list[tuple[str, str, bool]],
) -> None:
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
