"""Thin MainWindow integration tests for project-tree delete delegation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow

pytestmark = pytest.mark.unit


def test_main_window_tree_delete_delegates_to_workflow() -> None:
    delete_calls: list[str] = []
    bulk_calls: list[list[str]] = []
    host = SimpleNamespace(
        project_tree_action_workflow=lambda: SimpleNamespace(
            delete_paths=lambda path: delete_calls.append(path),
            bulk_delete=lambda paths: bulk_calls.append(list(paths)),
        )
    )
    workflow = ProjectTreeUiWorkflow(cast(Any, host))

    workflow.handle_tree_delete("/tmp/example.txt")
    workflow.handle_tree_bulk_delete(["/tmp/one.py", "/tmp/two.py"])

    assert delete_calls == ["/tmp/example.txt"]
    assert bulk_calls == [["/tmp/one.py", "/tmp/two.py"]]


def test_main_window_tree_clipboard_keys_update_internal_clipboard() -> None:
    host = SimpleNamespace(
        tree_clipboard_paths=[],
        tree_clipboard_cut=False,
        project_tree_presenter=lambda: SimpleNamespace(
            selected_paths=lambda: [("/tmp/example.txt", "example.txt", False)],
            selected_destination_directory=lambda: "/tmp",
        ),
        set_tree_clipboard_paths=lambda paths: host.__setattr__("tree_clipboard_paths", list(paths)),
        set_tree_clipboard_cut=lambda cut: host.__setattr__("tree_clipboard_cut", cut),
        project_tree_action_coordinator=lambda: SimpleNamespace(
            handle_paste=lambda **kwargs: ([], [], False),
        ),
    )
    workflow = ProjectTreeUiWorkflow(cast(Any, host))

    workflow.handle_project_tree_copy_key()
    assert host.tree_clipboard_paths == ["/tmp/example.txt"]
    assert host.tree_clipboard_cut is False

    workflow.handle_project_tree_cut_key()
    assert host.tree_clipboard_paths == ["/tmp/example.txt"]
    assert host.tree_clipboard_cut is True
