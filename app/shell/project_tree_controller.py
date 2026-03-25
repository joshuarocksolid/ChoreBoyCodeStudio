"""Project-tree operation coordination helpers for shell layer."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Generic, Optional, Protocol, TypeVar

from app.intelligence.import_rewrite import ImportRewritePreview, apply_import_rewrites, plan_import_rewrites
from app.project.file_operation_models import ImportUpdatePolicy


class TreeEditorWidget(Protocol):
    def set_breakpoints(self, breakpoints: set[int]) -> None: ...
    def set_language_for_path(self, file_path: str) -> None: ...
    def deleteLater(self) -> None: ...  # noqa: N802


W = TypeVar("W", bound=TreeEditorWidget)


class ProjectTreeController(Generic[W]):
    """Coordinates editor/path updates for tree delete/move operations."""

    def close_deleted_editor_paths(
        self,
        deleted_path: str,
        *,
        editor_widgets_by_path: dict[str, W],
        tab_index_for_path: Callable[[str], int],
        remove_tab_at_index: Callable[[int], None],
        release_editor_widget: Callable[[W], None],
        close_editor_file: Callable[[str], None],
        breakpoints_by_file: dict[str, set[int]],
        refresh_breakpoints_list: Callable[[], None],
        record_deleted_path: Optional[Callable[[str], None]] = None,
    ) -> None:
        deleted_resolved = str(Path(deleted_path).resolve())
        for open_path in list(editor_widgets_by_path.keys()):
            if open_path != deleted_resolved and not open_path.startswith(f"{deleted_resolved}/"):
                continue
            widget = editor_widgets_by_path.pop(open_path)
            tab_index = tab_index_for_path(open_path)
            if tab_index >= 0:
                remove_tab_at_index(tab_index)
            release_editor_widget(widget)
            close_editor_file(open_path)
            breakpoints_by_file.pop(open_path, None)
        refresh_breakpoints_list()
        if record_deleted_path is not None:
            record_deleted_path(deleted_resolved)

    def apply_path_move_updates(
        self,
        source_path: str,
        destination_path: str,
        *,
        remap_editor_paths: Callable[[str, str], dict[str, str]],
        editor_widgets_by_path: dict[str, W],
        tab_index_for_path: Callable[[str], int],
        update_tab_path_and_name: Callable[[int, str], None],
        breakpoints_by_file: dict[str, set[int]],
        apply_breakpoints_to_widget: Callable[[W, set[int]], None],
        update_widget_language: Callable[[W, str], None],
        refresh_breakpoints_list: Callable[[], None],
        maybe_rewrite_imports: Callable[[str, str], None],
        remap_file_lineage: Optional[Callable[[dict[str, str]], None]] = None,
    ) -> None:
        remapped_paths = remap_editor_paths(source_path, destination_path)
        for old_path, new_path in remapped_paths.items():
            widget = editor_widgets_by_path.pop(old_path, None)
            if widget is None:
                continue
            editor_widgets_by_path[new_path] = widget
            tab_index = tab_index_for_path(old_path)
            if tab_index >= 0:
                update_tab_path_and_name(tab_index, new_path)
            breakpoints = breakpoints_by_file.pop(old_path, None)
            if breakpoints is not None:
                breakpoints_by_file[new_path] = breakpoints
                apply_breakpoints_to_widget(widget, breakpoints)
            update_widget_language(widget, new_path)

        refresh_breakpoints_list()
        if remap_file_lineage is not None and remapped_paths:
            remap_file_lineage(dict(remapped_paths))
        maybe_rewrite_imports(source_path, destination_path)

    def maybe_rewrite_imports_for_move(
        self,
        *,
        project_root: Optional[str],
        source_path: str,
        destination_path: str,
        resolve_policy_for_operation: Callable[[], ImportUpdatePolicy],
        request_confirmation: Callable[[str], bool],
        show_warning: Callable[[str], None],
        on_applied: Optional[Callable[[list[ImportRewritePreview]], None]] = None,
    ) -> None:
        if not project_root:
            return
        source = Path(source_path).resolve()
        destination = Path(destination_path).resolve()
        if source.suffix != ".py" and destination.suffix != ".py":
            return
        project_root_path = Path(project_root).resolve()
        try:
            old_relative = source.relative_to(project_root_path).as_posix()
            new_relative = destination.relative_to(project_root_path).as_posix()
        except ValueError:
            return

        previews = plan_import_rewrites(project_root, old_relative, new_relative)
        if not previews:
            return

        policy = resolve_policy_for_operation()
        if policy == ImportUpdatePolicy.NEVER:
            return
        if policy == ImportUpdatePolicy.ASK:
            details = "\n".join(
                f"- {Path(preview.file_path).name}: lines {', '.join(str(line) for line in preview.changed_line_numbers)}"
                for preview in previews[:10]
            )
            if not request_confirmation(
                (
                    "Update imports for moved module?\n\n"
                    f"{len(previews)} file(s) would be modified.\n{details}"
                )
            ):
                return

        try:
            apply_import_rewrites(previews)
        except OSError as exc:
            show_warning(f"Could not rewrite imports: {exc}")
            return
        if on_applied is not None:
            on_applied(previews)
