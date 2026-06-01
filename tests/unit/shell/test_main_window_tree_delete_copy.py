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
