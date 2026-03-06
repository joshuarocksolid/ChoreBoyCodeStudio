"""Unit tests for re-linting open files after runtime module probe completes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


def _make_window_with_open_files(file_paths: list[str]) -> tuple[MainWindow, list[str]]:
    """Create a bare MainWindow with stub editor widgets and diagnostics tracking."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)

    window_any._editor_widgets_by_path = {
        fp: SimpleNamespace(toPlainText=lambda: "")
        for fp in file_paths
    }
    window_any._diagnostics_enabled = True
    window_any._diagnostics_realtime = True

    relinted: list[str] = []

    def fake_render_lint(file_path: str, *, trigger: str) -> None:
        relinted.append(file_path)

    window_any._render_lint_diagnostics_for_file = fake_render_lint
    window_any._render_merged_problems_panel = lambda: None

    return window, relinted


def test_relint_open_python_files_lints_all_py_files() -> None:
    window, relinted = _make_window_with_open_files([
        "/project/main.py",
        "/project/utils.py",
        "/project/README.md",
    ])

    MainWindow._relint_open_python_files(window)

    assert sorted(relinted) == ["/project/main.py", "/project/utils.py"]


def test_relint_open_python_files_skips_non_py() -> None:
    window, relinted = _make_window_with_open_files([
        "/project/config.json",
        "/project/notes.txt",
    ])

    MainWindow._relint_open_python_files(window)

    assert relinted == []


def test_relint_open_python_files_handles_empty_editor_set() -> None:
    window, relinted = _make_window_with_open_files([])

    MainWindow._relint_open_python_files(window)

    assert relinted == []


def test_probe_on_success_triggers_relint() -> None:
    """After probe completes, open Python files must be re-linted."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)

    window_any._known_runtime_modules = None
    window_any._state_root = None
    window_any._logger = SimpleNamespace(
        info=lambda *_a, **_kw: None,
        warning=lambda *_a, **_kw: None,
    )

    relint_calls: list[bool] = []
    window_any._relint_open_python_files = lambda: relint_calls.append(True)

    captured_on_success = {}

    class FakeBackgroundTasks:
        def run(self, *, key: str, task: Any, on_success: Any, on_error: Any) -> None:
            captured_on_success[key] = on_success

    window_any._background_tasks = FakeBackgroundTasks()

    MainWindow._start_runtime_module_probe(window)

    assert "runtime_module_probe" in captured_on_success

    modules = frozenset(["os", "sys", "json"])
    captured_on_success["runtime_module_probe"](modules)

    assert window_any._known_runtime_modules == modules
    assert relint_calls == [True]


def test_probe_on_success_empty_modules_logs_warning_and_skips_relint() -> None:
    """Empty probe payload should not relint and should be diagnosable."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)

    warning_messages: list[str] = []
    window_any._known_runtime_modules = None
    window_any._state_root = None
    window_any._logger = SimpleNamespace(
        info=lambda *_a, **_kw: None,
        warning=lambda message, *_a, **_kw: warning_messages.append(str(message)),
    )
    relint_calls: list[bool] = []
    window_any._relint_open_python_files = lambda: relint_calls.append(True)

    captured_on_success = {}

    class FakeBackgroundTasks:
        def run(self, *, key: str, task: Any, on_success: Any, on_error: Any) -> None:
            captured_on_success[key] = on_success

    window_any._background_tasks = FakeBackgroundTasks()

    MainWindow._start_runtime_module_probe(window)
    captured_on_success["runtime_module_probe"](frozenset())

    assert relint_calls == []
    assert warning_messages


def test_probe_on_success_empty_modules_user_initiated_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual refresh should show a warning when probe returns no modules."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)

    window_any._known_runtime_modules = None
    window_any._state_root = None
    window_any._logger = SimpleNamespace(
        info=lambda *_a, **_kw: None,
        warning=lambda *_a, **_kw: None,
    )
    window_any._relint_open_python_files = lambda: None

    shown_messages: list[str] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, _title, text: shown_messages.append(text),
    )

    captured_on_success = {}

    class FakeBackgroundTasks:
        def run(self, *, key: str, task: Any, on_success: Any, on_error: Any) -> None:
            captured_on_success[key] = on_success

    window_any._background_tasks = FakeBackgroundTasks()

    MainWindow._start_runtime_module_probe(window, user_initiated=True)
    captured_on_success["runtime_module_probe"](frozenset())

    assert shown_messages
