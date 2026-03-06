"""Unit tests for MainWindow run/debug command routing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def test_handle_run_action_routes_to_active_file_entry() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: SimpleNamespace(file_path="/tmp/project/a.py"))
    window_any._breakpoints_by_file = {}

    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_action(window)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_SCRIPT
    assert calls[0]["entry_file"] == str(Path("/tmp/project/a.py").expanduser().resolve())
    assert calls[0]["breakpoints"] is None


def test_handle_debug_action_routes_to_active_file_and_collects_breakpoints() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: SimpleNamespace(file_path="/tmp/project/debug.py"))
    window_any._breakpoints_by_file = {
        "/tmp/project/debug.py": {9, 2},
        "/tmp/project/other.py": {1},
    }

    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_debug_action(window)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_DEBUG
    assert calls[0]["entry_file"] == str(Path("/tmp/project/debug.py").expanduser().resolve())
    assert calls[0]["breakpoints"] == [
        {"file_path": "/tmp/project/debug.py", "line_number": 2},
        {"file_path": "/tmp/project/debug.py", "line_number": 9},
        {"file_path": "/tmp/project/other.py", "line_number": 1},
    ]


def test_handle_run_project_action_uses_project_entry_resolution() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._resolve_project_entry_for_project_run = lambda: "app.py"
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_project_action(window)

    assert started is True
    assert calls == [{"mode": constants.RUN_MODE_PYTHON_SCRIPT, "entry_file": "app.py"}]


def test_start_active_file_session_rejects_non_python_file(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: SimpleNamespace(file_path="/tmp/project/readme.txt"))
    window_any._breakpoints_by_file = {}
    window_any._start_session = lambda **_kwargs: True

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = MainWindow._start_active_file_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is False
    assert warnings == [("Run unavailable", "Active file must be a Python file.")]
