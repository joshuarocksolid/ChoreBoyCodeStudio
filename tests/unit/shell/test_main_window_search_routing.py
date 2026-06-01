"""Unit tests for search result navigation routing in the shell."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow

pytestmark = pytest.mark.unit


def _make_search_workflow() -> tuple[ProjectTreeUiWorkflow, list[tuple[str, int | None, bool]]]:
    calls: list[tuple[str, int | None, bool]] = []

    host = SimpleNamespace(
        open_file_at_line=lambda file_path, line_number, preview=False: calls.append(
            (file_path, line_number, preview)
        ),
    )
    return ProjectTreeUiWorkflow(host), calls  # type: ignore[arg-type]


def test_handle_search_open_file_at_line_uses_permanent_open() -> None:
    workflow, calls = _make_search_workflow()

    workflow.handle_search_open_file_at_line("/tmp/project/src/main.py", 27)

    assert calls == [("/tmp/project/src/main.py", 27, False)]


def test_handle_search_preview_file_at_line_uses_preview_open() -> None:
    workflow, calls = _make_search_workflow()

    workflow.handle_search_preview_file_at_line("/tmp/project/src/main.py", 11)

    assert calls == [("/tmp/project/src/main.py", 11, True)]
