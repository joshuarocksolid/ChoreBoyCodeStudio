"""Project-tree context menu construction and dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtCore import QSize
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QAction, QApplication, QMenu

from app.shell.icon_provider import (
    copy_icon,
    copy_path_icon,
    cut_icon,
    duplicate_icon,
    history_icon,
    new_file_icon,
    new_folder_icon,
    paste_icon,
    rename_icon,
    reveal_icon,
    source_root_icon,
    source_root_unmark_icon,
    trash_icon,
)
from app.shell.project_tree_shortcuts import (
    configured_tree_shortcut,
    effective_shortcuts_for_window,
    project_tree_copy_shortcut_id,
    project_tree_cut_shortcut_id,
    project_tree_delete_shortcut_id,
    project_tree_paste_shortcut_id,
    project_tree_rename_shortcut_id,
)
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toolbar_icons import icon_run, icon_run_file


_TREE_MENU_ICON_SIZE = 16


def _tree_menu_shortcuts(window: Any) -> dict[str, str | None]:
    effective = effective_shortcuts_for_window(window)
    return {
        "rename": configured_tree_shortcut(effective, project_tree_rename_shortcut_id()),
        "delete": configured_tree_shortcut(effective, project_tree_delete_shortcut_id()),
        "copy": configured_tree_shortcut(effective, project_tree_copy_shortcut_id()),
        "cut": configured_tree_shortcut(effective, project_tree_cut_shortcut_id()),
        "paste": configured_tree_shortcut(effective, project_tree_paste_shortcut_id()),
    }


def _tree_menu_icons(tokens: ShellThemeTokens) -> dict[str, QIcon]:
    primary = tokens.icon_primary or tokens.text_primary
    muted = tokens.icon_muted or primary
    danger = tokens.diag_error_color or primary
    running = tokens.debug_running_color or primary
    return {
        "new_file": new_file_icon(primary, muted),
        "new_folder": new_folder_icon(primary, muted),
        "rename": rename_icon(primary),
        "trash": trash_icon(danger),
        "duplicate": duplicate_icon(primary),
        "copy": copy_icon(primary),
        "cut": cut_icon(primary),
        "paste": paste_icon(primary),
        "copy_path": copy_path_icon(muted),
        "reveal": reveal_icon(muted),
        "source_root": source_root_icon(primary),
        "source_root_unmark": source_root_unmark_icon(primary),
        "history": history_icon(primary),
        "run": icon_run(color=running),
        "run_file": icon_run_file(color=running),
    }


def _new_tree_menu(window: Any) -> tuple[QMenu, dict[str, QIcon]]:
    menu = QMenu(window)
    set_icon_size = getattr(menu, "setIconSize", None)
    if callable(set_icon_size):
        set_icon_size(QSize(_TREE_MENU_ICON_SIZE, _TREE_MENU_ICON_SIZE))
    return menu, _tree_menu_icons(window.current_theme_tokens())


def _add_menu_action(
    menu: QMenu,
    icon: QIcon,
    label: str,
    *,
    shortcut: str | None = None,
    status_tip: str | None = None,
    enabled: bool = True,
) -> QAction:
    action = QAction(icon, label, menu)
    if shortcut:
        action.setShortcut(shortcut)
    if status_tip:
        action.setStatusTip(status_tip)
        action.setToolTip(status_tip)
    action.setEnabled(enabled)
    menu.addAction(action)
    return action


def show_single_item_tree_context_menu(
    window: Any,
    position: object,
    entry: tuple[str, str, bool],
) -> None:
    assert window._project_tree_widget is not None
    absolute_path, relative_path, is_directory = entry

    menu, icons = _new_tree_menu(window)
    shortcuts = _tree_menu_shortcuts(window)
    new_file_action = _add_menu_action(menu, icons["new_file"], "New File…")
    new_folder_action = _add_menu_action(menu, icons["new_folder"], "New Folder…")
    menu.addSeparator()
    rename_action = _add_menu_action(
        menu,
        icons["rename"],
        "Rename…",
        shortcut=shortcuts["rename"],
    )
    delete_action = _add_menu_action(
        menu,
        icons["trash"],
        "Move to Trash",
        shortcut=shortcuts["delete"],
        status_tip="Move the selected item to the trash.",
    )
    duplicate_action = _add_menu_action(menu, icons["duplicate"], "Duplicate")
    menu.addSeparator()
    copy_action = _add_menu_action(
        menu,
        icons["copy"],
        "Copy",
        shortcut=shortcuts["copy"],
    )
    cut_action = _add_menu_action(
        menu,
        icons["cut"],
        "Cut",
        shortcut=shortcuts["cut"],
    )
    paste_action = _add_menu_action(
        menu,
        icons["paste"],
        "Paste",
        shortcut=shortcuts["paste"],
    )
    menu.addSeparator()
    copy_path_action = _add_menu_action(menu, icons["copy_path"], "Copy Path")
    copy_relative_path_action = _add_menu_action(
        menu,
        icons["copy_path"],
        "Copy Relative Path",
    )
    reveal_action = _add_menu_action(
        menu,
        icons["reveal"],
        "Reveal in File Manager",
        status_tip="Open this item in the system file manager.",
    )
    mark_source_root_action = None
    unmark_source_root_action = None
    if is_directory and window._loaded_project is not None:
        configured_roots = set(window._loaded_project.metadata.source_roots)
        normalized_relative = relative_path.replace("\\", "/").strip("/")
        menu.addSeparator()
        if normalized_relative in configured_roots:
            unmark_source_root_action = _add_menu_action(
                menu,
                icons["source_root_unmark"],
                "Unmark Sources Root",
                status_tip="Remove this folder from the project's source roots.",
            )
        else:
            mark_source_root_action = _add_menu_action(
                menu,
                icons["source_root"],
                "Mark as Sources Root",
                status_tip="Use this folder as a project source root.",
            )
    local_history_action = None
    if not is_directory:
        local_history_action = _add_menu_action(
            menu,
            icons["history"],
            "Local History…",
            status_tip="Review saved local-history entries for this file.",
        )
    run_file_action = None
    run_file_with_args_action = None
    set_entry_point_action = None
    if (
        not is_directory
        and window._loaded_project is not None
        and Path(absolute_path).suffix.lower() == ".py"
    ):
        menu.addSeparator()
        run_is_idle = not window._run_service.supervisor.is_running()
        run_file_action = _add_menu_action(
            menu,
            icons["run"],
            "Run",
            status_tip="Run this Python file. Output appears in the Run Log tab.",
            enabled=run_is_idle,
        )
        run_file_with_args_action = _add_menu_action(
            menu,
            icons["run_file"],
            "Run With Arguments…",
            status_tip="Run this Python file with custom arguments.",
            enabled=run_is_idle,
        )
        set_entry_point_action = _add_menu_action(
            menu,
            icons["run"],
            "Set as Entry Point",
            status_tip="Use this file as the project's default entry point.",
        )
        if relative_path == window._loaded_project.metadata.default_entry:
            set_entry_point_action.setEnabled(False)

    paste_action.setEnabled(len(window._tree_clipboard_paths) > 0)
    chosen = menu.exec_(window._project_tree_widget.viewport().mapToGlobal(position))
    workflow = window._project_tree_ui_workflow
    if chosen is None:
        return

    if chosen == new_file_action:
        workflow.handle_tree_new_file(absolute_path if is_directory else str(Path(absolute_path).parent))
    elif chosen == new_folder_action:
        workflow.handle_tree_new_folder(absolute_path if is_directory else str(Path(absolute_path).parent))
    elif chosen == rename_action:
        workflow.handle_tree_rename(absolute_path)
    elif chosen == delete_action:
        workflow.handle_tree_delete(absolute_path)
    elif chosen == duplicate_action:
        workflow.handle_tree_duplicate(absolute_path)
    elif chosen == copy_action:
        window._tree_clipboard_paths = [absolute_path]
        window._tree_clipboard_cut = False
    elif chosen == cut_action:
        window._tree_clipboard_paths = [absolute_path]
        window._tree_clipboard_cut = True
    elif chosen == paste_action:
        workflow.handle_tree_paste(absolute_path if is_directory else str(Path(absolute_path).parent))
    elif chosen == copy_path_action:
        QApplication.clipboard().setText(absolute_path)
    elif chosen == copy_relative_path_action:
        QApplication.clipboard().setText(relative_path)
    elif chosen == reveal_action:
        workflow.reveal_path_in_file_manager(absolute_path)
    elif not is_directory and local_history_action is not None and chosen == local_history_action:
        window._local_history_workflow.show_local_history_for_path(absolute_path)
    elif run_file_action is not None and chosen == run_file_action:
        window._run_launch_workflow.handle_tree_run_file(absolute_path)
    elif run_file_with_args_action is not None and chosen == run_file_with_args_action:
        window._run_launch_workflow.handle_tree_run_file_with_arguments(absolute_path)
    elif set_entry_point_action is not None and chosen == set_entry_point_action:
        workflow.set_project_entry_point(relative_path)
    elif mark_source_root_action is not None and chosen == mark_source_root_action:
        workflow.handle_tree_mark_source_root(relative_path)
    elif unmark_source_root_action is not None and chosen == unmark_source_root_action:
        workflow.handle_tree_unmark_source_root(relative_path)


def show_bulk_tree_context_menu(
    window: Any,
    position: object,
    selected: list[tuple[str, str, bool]],
) -> None:
    assert window._project_tree_widget is not None
    abs_paths = [entry[0] for entry in selected]

    menu, icons = _new_tree_menu(window)
    shortcuts = _tree_menu_shortcuts(window)
    delete_action = _add_menu_action(
        menu,
        icons["trash"],
        f"Move {len(selected)} Items to Trash",
        shortcut=shortcuts["delete"],
        status_tip="Move the selected items to the trash.",
    )
    duplicate_action = _add_menu_action(
        menu,
        icons["duplicate"],
        f"Duplicate {len(selected)} Items",
    )
    menu.addSeparator()
    copy_action = _add_menu_action(
        menu,
        icons["copy"],
        "Copy",
        shortcut=shortcuts["copy"],
    )
    cut_action = _add_menu_action(
        menu,
        icons["cut"],
        "Cut",
        shortcut=shortcuts["cut"],
    )
    paste_action = _add_menu_action(
        menu,
        icons["paste"],
        "Paste",
        shortcut=shortcuts["paste"],
    )
    menu.addSeparator()
    copy_path_action = _add_menu_action(menu, icons["copy_path"], "Copy Paths")
    copy_relative_path_action = _add_menu_action(
        menu,
        icons["copy_path"],
        "Copy Relative Paths",
    )

    paste_action.setEnabled(len(window._tree_clipboard_paths) > 0)
    chosen = menu.exec_(window._project_tree_widget.viewport().mapToGlobal(position))
    if chosen is None:
        return

    workflow = window._project_tree_ui_workflow
    if chosen == delete_action:
        workflow.handle_tree_bulk_delete(abs_paths)
    elif chosen == duplicate_action:
        workflow.handle_tree_bulk_duplicate(abs_paths)
    elif chosen == copy_action:
        window._tree_clipboard_paths = list(abs_paths)
        window._tree_clipboard_cut = False
    elif chosen == cut_action:
        window._tree_clipboard_paths = list(abs_paths)
        window._tree_clipboard_cut = True
    elif chosen == paste_action:
        first_abs, _, first_is_dir = selected[0]
        dest = first_abs if first_is_dir else str(Path(first_abs).parent)
        workflow.handle_tree_paste(dest)
    elif chosen == copy_path_action:
        QApplication.clipboard().setText("\n".join(abs_paths))
    elif chosen == copy_relative_path_action:
        rel_paths = [entry[1] for entry in selected]
        QApplication.clipboard().setText("\n".join(rel_paths))
