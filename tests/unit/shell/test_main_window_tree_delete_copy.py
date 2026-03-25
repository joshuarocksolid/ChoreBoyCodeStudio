"""Unit tests for project-tree move-to-trash copy in MainWindow."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QMessageBox  # noqa: E402

from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


def test_tree_delete_confirmation_uses_move_to_trash_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    handled_paths: list[str] = []
    window_any._project_tree_action_coordinator = SimpleNamespace(
        handle_delete=lambda path: handled_paths.append(path) or None
    )

    prompts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.question",
        lambda _parent, title, text, *_args: prompts.append((title, text)) or QMessageBox.Yes,
    )

    MainWindow._handle_tree_delete(window, "/tmp/example.txt")

    assert handled_paths == ["/tmp/example.txt"]
    assert prompts == [("Move to Trash", "Move 'example.txt' to trash?")]


def test_tree_bulk_delete_failure_warning_uses_move_to_trash_title(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._project_tree_action_coordinator = SimpleNamespace(
        handle_bulk_delete=lambda _paths: (["one.py: permission denied"], [])
    )
    window_any._capture_text_history_snapshots = lambda _paths: []
    window_any._record_local_history_transaction = lambda *_args, **_kwargs: None
    window_any._filter_snapshots_for_paths = lambda snapshots, _paths: snapshots

    prompts: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.question",
        lambda _parent, title, text, *_args: prompts.append((title, text)) or QMessageBox.Yes,
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    MainWindow._handle_tree_bulk_delete(window, ["/tmp/one.py", "/tmp/two.py"])

    assert prompts
    assert prompts[0][0] == "Move to Trash"
    assert "cannot be undone" not in prompts[0][1].lower()
    assert warnings == [("Move to Trash", "one.py: permission denied")]
