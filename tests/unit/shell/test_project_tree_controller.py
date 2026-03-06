"""Unit tests for shell project-tree controller logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_operation_models import ImportUpdatePolicy
from app.shell.project_tree_controller import ProjectTreeController

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


def test_close_deleted_editor_paths_removes_nested_entries() -> None:
    controller = ProjectTreeController()
    widget_a = _FakeWidget()
    widget_b = _FakeWidget()
    editor_widgets = {
        "/tmp/project/app.py": widget_a,
        "/tmp/project/sub/module.py": widget_b,
    }
    closed: list[str] = []
    removed_tabs: list[int] = []
    breakpoints = {"/tmp/project/app.py": {10}, "/tmp/project/sub/module.py": {4}}

    controller.close_deleted_editor_paths(
        "/tmp/project",
        editor_widgets_by_path=editor_widgets,
        tab_index_for_path=lambda _path: 0,
        remove_tab_at_index=removed_tabs.append,
        release_editor_widget=lambda widget: widget.deleteLater(),
        close_editor_file=closed.append,
        breakpoints_by_file=breakpoints,
        refresh_breakpoints_list=lambda: None,
    )

    assert editor_widgets == {}
    assert sorted(closed) == ["/tmp/project/app.py", "/tmp/project/sub/module.py"]
    assert breakpoints == {}
    assert removed_tabs == [0, 0]
    assert widget_a.released is True and widget_b.released is True


def test_apply_path_move_updates_remaps_widgets_breakpoints_and_tabs() -> None:
    controller = ProjectTreeController()
    widget = _FakeWidget()
    editor_widgets = {"/tmp/project/old.py": widget}
    breakpoints = {"/tmp/project/old.py": {12}}
    updated_tabs: list[tuple[int, str]] = []
    rewrites: list[tuple[str, str]] = []

    controller.apply_path_move_updates(
        "/tmp/project/old.py",
        "/tmp/project/new.py",
        remap_editor_paths=lambda _old, _new: {"/tmp/project/old.py": "/tmp/project/new.py"},
        editor_widgets_by_path=editor_widgets,
        tab_index_for_path=lambda _path: 3,
        update_tab_path_and_name=lambda index, path: updated_tabs.append((index, path)),
        breakpoints_by_file=breakpoints,
        apply_breakpoints_to_widget=lambda w, values: w.set_breakpoints(values),  # type: ignore[attr-defined]
        update_widget_language=lambda w, path: w.set_language_for_path(path),  # type: ignore[attr-defined]
        refresh_breakpoints_list=lambda: None,
        maybe_rewrite_imports=lambda source, destination: rewrites.append((source, destination)),
    )

    assert "/tmp/project/new.py" in editor_widgets
    assert editor_widgets["/tmp/project/new.py"] is widget
    assert breakpoints == {"/tmp/project/new.py": {12}}
    assert widget.breakpoints == {12}
    assert widget.language_path == "/tmp/project/new.py"
    assert updated_tabs == [(3, "/tmp/project/new.py")]
    assert rewrites == [("/tmp/project/old.py", "/tmp/project/new.py")]


def test_apply_path_move_updates_remaps_nested_paths_for_directory_move() -> None:
    """Directory moves should remap all nested open editors and breakpoints."""
    controller = ProjectTreeController()
    widget_a = _FakeWidget()
    widget_b = _FakeWidget()
    editor_widgets = {
        "/tmp/project/pkg/a.py": widget_a,
        "/tmp/project/pkg/sub/b.py": widget_b,
    }
    breakpoints = {
        "/tmp/project/pkg/a.py": {2},
        "/tmp/project/pkg/sub/b.py": {7, 9},
    }
    updated_tabs: list[tuple[int, str]] = []
    rewrites: list[tuple[str, str]] = []

    controller.apply_path_move_updates(
        "/tmp/project/pkg",
        "/tmp/project/lib",
        remap_editor_paths=lambda _old, _new: {
            "/tmp/project/pkg/a.py": "/tmp/project/lib/a.py",
            "/tmp/project/pkg/sub/b.py": "/tmp/project/lib/sub/b.py",
        },
        editor_widgets_by_path=editor_widgets,
        tab_index_for_path=lambda path: 1 if path.endswith("a.py") else 2,
        update_tab_path_and_name=lambda index, path: updated_tabs.append((index, path)),
        breakpoints_by_file=breakpoints,
        apply_breakpoints_to_widget=lambda w, values: w.set_breakpoints(values),  # type: ignore[attr-defined]
        update_widget_language=lambda w, path: w.set_language_for_path(path),  # type: ignore[attr-defined]
        refresh_breakpoints_list=lambda: None,
        maybe_rewrite_imports=lambda source, destination: rewrites.append((source, destination)),
    )

    assert sorted(editor_widgets.keys()) == [
        "/tmp/project/lib/a.py",
        "/tmp/project/lib/sub/b.py",
    ]
    assert breakpoints == {
        "/tmp/project/lib/a.py": {2},
        "/tmp/project/lib/sub/b.py": {7, 9},
    }
    assert widget_a.breakpoints == {2}
    assert widget_b.breakpoints == {7, 9}
    assert widget_a.language_path == "/tmp/project/lib/a.py"
    assert widget_b.language_path == "/tmp/project/lib/sub/b.py"
    assert updated_tabs == [
        (1, "/tmp/project/lib/a.py"),
        (2, "/tmp/project/lib/sub/b.py"),
    ]
    assert rewrites == [("/tmp/project/pkg", "/tmp/project/lib")]


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
