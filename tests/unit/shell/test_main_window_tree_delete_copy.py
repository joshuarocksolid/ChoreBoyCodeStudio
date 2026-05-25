"""Thin MainWindow integration tests for project-tree delete delegation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def test_main_window_tree_delete_delegates_to_workflow() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    delete_calls: list[str] = []
    bulk_calls: list[list[str]] = []
    window_any._project_tree_action_workflow = SimpleNamespace(
        delete_paths=lambda path: delete_calls.append(path),
        bulk_delete=lambda paths: bulk_calls.append(list(paths)),
    )

    MainWindow._handle_tree_delete(window, "/tmp/example.txt")
    MainWindow._handle_tree_bulk_delete(window, ["/tmp/one.py", "/tmp/two.py"])

    assert delete_calls == ["/tmp/example.txt"]
    assert bulk_calls == [["/tmp/one.py", "/tmp/two.py"]]
