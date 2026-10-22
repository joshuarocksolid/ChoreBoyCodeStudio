"""Unit tests for shell project-tree controller logic."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.project.file_operation_models import ImportUpdatePolicy  # noqa: E402
from app.shell.breakpoint_store import BreakpointStore  # noqa: E402
from app.shell.editor_workspace_controller import EditorWorkspaceController  # noqa: E402
from app.shell.project_tree_controller import ProjectTreeController  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeWidget:
    def __init__(self) -> None:
        self.breakpoints: set[int] = set()
        self.language_path = ""
        self.released = False

    def set_breakpoints(self, breakpoints: set[int]) -> None:
        self.breakpoints = set(breakpoints)

    def set_language_for_path(self, path: str) -> None:
        self.language_path = path

    def deleteLater(self) -> None:  # noqa: N802
        self.released = True


def _open_editors(tmp_path: Path, relative_paths: list[str]) -> tuple[EditorManager, EditorWorkspaceController, list[str]]:
    manager = EditorManager()
    workspace = EditorWorkspaceController(lambda: manager)
    opened: list[str] = []
    for relative_path in relative_paths:
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("x = 1\n", encoding="utf-8")
        tab = manager.open_file(str(file_path)).tab
        workspace.register_editor(tab.buffer_id, _FakeWidget())  # type: ignore[arg-type]
        opened.append(tab.file_path)
    return manager, workspace, opened


def test_close_deleted_editor_paths_removes_nested_entries(tmp_path: Path) -> None:
    controller = ProjectTreeController()
    manager, workspace, (app_path, module_path) = _open_editors(tmp_path, ["project/app.py", "project/sub/module.py"])
    widgets = [workspace.widget_for_path(app_path), workspace.widget_for_path(module_path)]
    removed_tabs: list[int] = []
    breakpoint_store = BreakpointStore()
    breakpoint_store.set_line_enabled(app_path, 10, enabled=True)
    breakpoint_store.set_line_enabled(module_path, 4, enabled=True)
    deleted_records: list[str] = []
    project_path = str((tmp_path / "project").resolve())

    controller.close_deleted_editor_paths(
        project_path,
        open_editor_paths=workspace.open_editor_paths,
        pop_editor_for_path=workspace.pop_editor_for_path,
        tab_index_for_path=lambda _path: 0,
        remove_tab_at_index=removed_tabs.append,
        release_editor_widget=lambda widget: widget.deleteLater(),  # type: ignore[attr-defined]
        close_editor_file=lambda file_path: manager.close_file(file_path),
        breakpoint_store=breakpoint_store,
        refresh_breakpoints_list=lambda: None,
        record_deleted_path=deleted_records.append,
    )

    assert workspace.editor_widgets_by_path == {}
    assert manager.open_paths() == []
    assert breakpoint_store.has_any_breakpoints() is False
    assert removed_tabs == [0, 0]
    assert all(widget is not None and widget.released for widget in widgets)  # type: ignore[attr-defined]
    assert deleted_records == [project_path]


def _apply_move(
    controller: ProjectTreeController,
    manager: EditorManager,
    workspace: EditorWorkspaceController,
    breakpoint_store: BreakpointStore,
    source: str,
    destination: str,
) -> dict[str, list]:
    calls: dict[str, list] = {"tabs": [], "rewrites": [], "lineage": [], "migrated": []}
    controller.apply_path_move_updates(
        source,
        destination,
        remap_editor_paths=manager.remap_paths_for_move,
        widget_for_path=workspace.widget_for_path,
        tab_index_for_path=lambda path: manager.open_paths().index(path),
        update_tab_path_and_name=lambda index, path: calls["tabs"].append((index, path)),
        breakpoint_store=breakpoint_store,
        apply_breakpoints_to_widget=lambda w, values: w.set_breakpoints(values),  # type: ignore[attr-defined]
        update_widget_language=lambda w, path: w.set_language_for_path(path),  # type: ignore[attr-defined]
        refresh_breakpoints_list=lambda: None,
        maybe_rewrite_imports=lambda src, dst: calls["rewrites"].append((src, dst)),
        migrate_buffer_state=lambda old, new: calls["migrated"].append((old, new)),
        remap_file_lineage=calls["lineage"].append,
    )
    return calls


def test_apply_path_move_updates_keeps_widget_under_buffer_and_remaps_presentation(tmp_path: Path) -> None:
    controller = ProjectTreeController()
    manager, workspace, (old_path,) = _open_editors(tmp_path, ["project/old.py"])
    buffer_id = manager.get_tab(old_path).buffer_id  # type: ignore[union-attr]
    widget = workspace.widget_for_path(old_path)
    breakpoint_store = BreakpointStore()
    breakpoint_store.set_line_enabled(old_path, 12, enabled=True)
    new_path = str(tmp_path.resolve() / "project" / "new.py")

    calls = _apply_move(controller, manager, workspace, breakpoint_store, old_path, new_path)

    assert workspace.widget_for_path(new_path) is widget
    assert workspace.widget_for_path(old_path) is None
    assert workspace.widget_for_buffer_id(buffer_id) is widget
    assert breakpoint_store.lines_for_file(new_path) == {12}
    assert widget.breakpoints == {12}  # type: ignore[union-attr]
    assert widget.language_path == new_path  # type: ignore[union-attr]
    assert calls["tabs"] == [(0, new_path)]
    assert calls["migrated"] == [(old_path, new_path)]
    assert calls["rewrites"] == [(old_path, new_path)]
    assert calls["lineage"] == [{old_path: new_path}]


def test_apply_path_move_updates_remaps_nested_paths_for_directory_move(tmp_path: Path) -> None:
    """Directory moves should remap all nested open editors and breakpoints."""
    controller = ProjectTreeController()
    manager, workspace, (a_path, b_path) = _open_editors(tmp_path, ["project/pkg/a.py", "project/pkg/sub/b.py"])
    widget_a = workspace.widget_for_path(a_path)
    widget_b = workspace.widget_for_path(b_path)
    breakpoint_store = BreakpointStore()
    breakpoint_store.set_line_enabled(a_path, 2, enabled=True)
    breakpoint_store.set_line_enabled(b_path, 7, enabled=True)
    root = tmp_path.resolve() / "project"
    new_a = str(root / "lib" / "a.py")
    new_b = str(root / "lib" / "sub" / "b.py")

    calls = _apply_move(controller, manager, workspace, breakpoint_store, str(root / "pkg"), str(root / "lib"))

    assert workspace.open_editor_paths() == [new_a, new_b]
    assert workspace.widget_for_path(new_a) is widget_a
    assert workspace.widget_for_path(new_b) is widget_b
    assert breakpoint_store.lines_snapshot() == {new_a: {2}, new_b: {7}}
    assert widget_a.language_path == new_a  # type: ignore[union-attr]
    assert widget_b.language_path == new_b  # type: ignore[union-attr]
    assert calls["tabs"] == [(0, new_a), (1, new_b)]
    assert calls["lineage"] == [{a_path: new_a, b_path: new_b}]


def test_maybe_rewrite_imports_for_move_honors_ask_policy_cancel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller = ProjectTreeController()
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    source = project_root / "pkg" / "old.py"
    destination = project_root / "pkg" / "new.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x = 1\n", encoding="utf-8")

    class _Preview:
        file_path = str(source)
        changed_line_numbers = [1]

    monkeypatch.setattr(
        "app.shell.project_tree_controller.plan_import_rewrites",
        lambda *_args, **_kwargs: [_Preview()],
    )

    applied = {"value": False}
    monkeypatch.setattr(
        "app.shell.project_tree_controller.apply_import_rewrites",
        lambda *_args, **_kwargs: applied.__setitem__("value", True),
    )

    controller.maybe_rewrite_imports_for_move(
        project_root=str(project_root),
        source_path=str(source),
        destination_path=str(destination),
        resolve_policy_for_operation=lambda: ImportUpdatePolicy.ASK,
        request_confirmation=lambda _message: False,
        show_warning=lambda _details: None,
    )

    assert applied["value"] is False
