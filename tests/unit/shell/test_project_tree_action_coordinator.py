"""Unit tests for project-tree action coordinator."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.project.file_operation_models import FileOperationResult
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator

pytestmark = pytest.mark.unit


@dataclass
class _FakeWidget:
    released: bool = False

    def set_breakpoints(self, _breakpoints: set[int]) -> None:
        return

    def set_language_for_path(self, _file_path: str) -> None:
        return

    def deleteLater(self) -> None:  # noqa: N802
        self.released = True


class _FakeProjectTreeController:
    def __init__(self) -> None:
        self.close_calls: list[str] = []
        self.move_calls: list[tuple[str, str]] = []

    def close_deleted_editor_paths(self, deleted_path: str, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        self.close_calls.append(deleted_path)

    def apply_path_move_updates(self, source_path: str, destination_path: str, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        self.move_calls.append((source_path, destination_path))


def _coordinator(
    fake_tree_controller: _FakeProjectTreeController,
) -> tuple[ProjectTreeActionCoordinator[_FakeWidget], list[bool]]:
    reloaded = []

    coordinator = ProjectTreeActionCoordinator(
        project_tree_controller=fake_tree_controller,  # type: ignore[arg-type]
        editor_widgets_by_path={},
        tab_index_for_path=lambda _path: -1,
        remove_tab_at_index=lambda _index: None,
        release_editor_widget=lambda _widget: None,
        close_editor_file=lambda _path: None,
        breakpoints_by_file={},
        refresh_breakpoints_list=lambda: None,
        remap_editor_paths=lambda _old, _new: {},
        update_tab_path_and_name=lambda _index, _path: None,
        apply_breakpoints_to_widget=lambda _widget, _bps: None,
        update_widget_language=lambda _widget, _path: None,
        maybe_rewrite_imports=lambda _src, _dst: None,
        reload_project=lambda: reloaded.append(True),
    )
    return coordinator, reloaded


def test_handle_rename_applies_path_move_updates_and_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)
    monkeypatch.setattr(
        "app.shell.project_tree_action_coordinator.rename_path",
        lambda _src, _dst: FileOperationResult(success=True, message="ok"),
    )

    error = coordinator.handle_rename("/tmp/project/old.py", "new.py")

    assert error is None
    assert tree_controller.move_calls == [("/tmp/project/old.py", "/tmp/project/new.py")]
    assert reloaded == [True]


def test_handle_bulk_delete_collects_failures_and_still_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)

    def _delete(path: str) -> FileOperationResult:
        if path.endswith("bad.py"):
            return FileOperationResult(success=False, message="permission denied")
        return FileOperationResult(success=True, message="ok")

    monkeypatch.setattr("app.shell.project_tree_action_coordinator.delete_path", _delete)

    failures = coordinator.handle_bulk_delete(["/tmp/project/good.py", "/tmp/project/bad.py"])

    assert tree_controller.close_calls == ["/tmp/project/good.py"]
    assert failures == ["bad.py: permission denied"]
    assert reloaded == [True]


def test_handle_paste_cut_applies_moves_and_clears_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, _ = _coordinator(tree_controller)
    monkeypatch.setattr(
        "app.shell.project_tree_action_coordinator.move_path",
        lambda _src, _dst: FileOperationResult(success=True, message="ok"),
    )

    failures, next_paths, next_cut = coordinator.handle_paste(
        destination_directory="/tmp/project/dest",
        clipboard_paths=["/tmp/project/a.py", "/tmp/project/b.py"],
        clipboard_cut=True,
    )

    assert failures == []
    assert next_paths == []
    assert next_cut is False
    assert tree_controller.move_calls == [
        ("/tmp/project/a.py", "/tmp/project/dest/a.py"),
        ("/tmp/project/b.py", "/tmp/project/dest/b.py"),
    ]


def test_handle_new_file_rejects_path_separators() -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)

    error = coordinator.handle_new_file("/tmp/project", "../escape.py")

    assert error == "File name cannot include path separators."
    assert reloaded == []


def test_handle_rename_rejects_path_separators() -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)

    error = coordinator.handle_rename("/tmp/project/old.py", "../new.py")

    assert error == "New name cannot include path separators."
    assert tree_controller.move_calls == []
    assert reloaded == []


def test_handle_drop_move_rejects_folder_move_into_itself(tmp_path) -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)
    source = tmp_path / "folder"
    child = source / "child"
    child.mkdir(parents=True)

    error = coordinator.handle_drop_move(str(source), str(child))

    assert error == "Cannot move a folder into itself."
    assert tree_controller.move_calls == []
    assert reloaded == []


def test_handle_drop_move_returns_oserror_message(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree_controller = _FakeProjectTreeController()
    coordinator, reloaded = _coordinator(tree_controller)
    source = tmp_path / "project" / "a.py"
    target_dir = tmp_path / "project" / "target"
    target_dir.mkdir(parents=True)
    source.write_text("print('x')\n", encoding="utf-8")

    def _raise_oserror(_source: str, _destination: str) -> FileOperationResult:
        raise OSError("permission denied")

    monkeypatch.setattr("app.shell.project_tree_action_coordinator.move_path", _raise_oserror)

    error = coordinator.handle_drop_move(str(source), str(target_dir))

    assert error == "permission denied"
    assert tree_controller.move_calls == []
    assert reloaded == []
