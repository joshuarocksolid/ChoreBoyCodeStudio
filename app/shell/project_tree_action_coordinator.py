"""Coordinator for project-tree filesystem actions and editor side effects."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Generic, TypeVar

from app.project.file_operations import copy_path, create_directory, create_file, delete_path, duplicate_path, move_path, rename_path
from app.shell.project_tree_controller import ProjectTreeController, TreeEditorWidget


W = TypeVar("W", bound=TreeEditorWidget)


class ProjectTreeActionCoordinator(Generic[W]):
    """Executes project-tree actions and applies editor/breakpoint remaps."""

    def __init__(
        self,
        *,
        project_tree_controller: ProjectTreeController[W],
        editor_widgets_by_path: dict[str, W],
        tab_index_for_path: Callable[[str], int],
        remove_tab_at_index: Callable[[int], None],
        release_editor_widget: Callable[[W], None],
        close_editor_file: Callable[[str], None],
        breakpoints_by_file: dict[str, set[int]],
        refresh_breakpoints_list: Callable[[], None],
        remap_editor_paths: Callable[[str, str], dict[str, str]],
        update_tab_path_and_name: Callable[[int, str], None],
        apply_breakpoints_to_widget: Callable[[W, set[int]], None],
        update_widget_language: Callable[[W, str], None],
        maybe_rewrite_imports: Callable[[str, str], None],
        prune_semantic_state: Callable[[], None],
        reload_project: Callable[[], None],
    ) -> None:
        self._project_tree_controller = project_tree_controller
        self._editor_widgets_by_path = editor_widgets_by_path
        self._tab_index_for_path = tab_index_for_path
        self._remove_tab_at_index = remove_tab_at_index
        self._release_editor_widget = release_editor_widget
        self._close_editor_file = close_editor_file
        self._breakpoints_by_file = breakpoints_by_file
        self._refresh_breakpoints_list = refresh_breakpoints_list
        self._remap_editor_paths = remap_editor_paths
        self._update_tab_path_and_name = update_tab_path_and_name
        self._apply_breakpoints_to_widget = apply_breakpoints_to_widget
        self._update_widget_language = update_widget_language
        self._maybe_rewrite_imports = maybe_rewrite_imports
        self._prune_semantic_state = prune_semantic_state
        self._reload_project = reload_project

    def handle_new_file(self, destination_directory: str, file_name: str) -> str | None:
        result = create_file(str(Path(destination_directory) / file_name))
        if not result.success:
            return result.message
        self._reload_project()
        return None

    def handle_new_folder(self, destination_directory: str, folder_name: str) -> str | None:
        result = create_directory(str(Path(destination_directory) / folder_name))
        if not result.success:
            return result.message
        self._reload_project()
        return None

    def handle_rename(self, source_path: str, new_name: str) -> str | None:
        source = Path(source_path)
        destination = source.with_name(new_name)
        result = rename_path(str(source), str(destination))
        if not result.success:
            return result.message
        self.apply_path_move_updates(str(source), str(destination))
        self._reload_project()
        return None

    def handle_delete(self, target_path: str) -> str | None:
        result = delete_path(target_path)
        if not result.success:
            return result.message
        self.close_deleted_editor_paths(target_path)
        self._reload_project()
        return None

    def handle_duplicate(self, source_path: str) -> str | None:
        result = duplicate_path(source_path)
        if not result.success:
            return result.message
        self._reload_project()
        return None

    def handle_bulk_delete(self, paths: list[str]) -> list[str]:
        failed: list[str] = []
        for target_path in paths:
            result = delete_path(target_path)
            if result.success:
                self.close_deleted_editor_paths(target_path)
            else:
                failed.append(f"{Path(target_path).name}: {result.message}")
        self._reload_project()
        return failed

    def handle_bulk_duplicate(self, paths: list[str]) -> list[str]:
        failed: list[str] = []
        for source_path in paths:
            result = duplicate_path(source_path)
            if not result.success:
                failed.append(f"{Path(source_path).name}: {result.message}")
        self._reload_project()
        return failed

    def handle_paste(
        self,
        *,
        destination_directory: str,
        clipboard_paths: list[str],
        clipboard_cut: bool,
    ) -> tuple[list[str], list[str], bool]:
        if not clipboard_paths:
            return ([], clipboard_paths, clipboard_cut)
        dest_dir = Path(destination_directory).resolve()
        failed: list[str] = []
        for clipboard_path in list(clipboard_paths):
            source = Path(clipboard_path).resolve()
            destination = dest_dir / source.name
            if clipboard_cut:
                result = move_path(str(source), str(destination))
                if result.success:
                    self.apply_path_move_updates(str(source), str(destination))
                else:
                    failed.append(f"{source.name}: {result.message}")
            else:
                result = copy_path(str(source), str(destination))
                if not result.success:
                    failed.append(f"{source.name}: {result.message}")
        next_clipboard_paths = [] if clipboard_cut else list(clipboard_paths)
        next_clipboard_cut = False if clipboard_cut else clipboard_cut
        self._reload_project()
        return (failed, next_clipboard_paths, next_clipboard_cut)

    def handle_drop_move(self, source_path: str, target_path: str) -> str | None:
        source = Path(source_path).resolve()
        target = Path(target_path).resolve()
        destination_directory = target if target.is_dir() else target.parent
        destination = destination_directory / source.name
        result = move_path(str(source), str(destination))
        if not result.success:
            return result.message
        self.apply_path_move_updates(str(source), str(destination))
        self._reload_project()
        return None

    def close_deleted_editor_paths(self, deleted_path: str) -> None:
        self._project_tree_controller.close_deleted_editor_paths(
            deleted_path,
            editor_widgets_by_path=self._editor_widgets_by_path,
            tab_index_for_path=self._tab_index_for_path,
            remove_tab_at_index=self._remove_tab_at_index,
            release_editor_widget=self._release_editor_widget,
            close_editor_file=self._close_editor_file,
            breakpoints_by_file=self._breakpoints_by_file,
            refresh_breakpoints_list=self._refresh_breakpoints_list,
        )

    def apply_path_move_updates(self, source_path: str, destination_path: str) -> None:
        self._project_tree_controller.apply_path_move_updates(
            source_path,
            destination_path,
            remap_editor_paths=self._remap_editor_paths,
            editor_widgets_by_path=self._editor_widgets_by_path,
            tab_index_for_path=self._tab_index_for_path,
            update_tab_path_and_name=self._update_tab_path_and_name,
            breakpoints_by_file=self._breakpoints_by_file,
            apply_breakpoints_to_widget=self._apply_breakpoints_to_widget,
            update_widget_language=self._update_widget_language,
            refresh_breakpoints_list=self._refresh_breakpoints_list,
            maybe_rewrite_imports=self._maybe_rewrite_imports,
        )
        self._prune_semantic_state()
