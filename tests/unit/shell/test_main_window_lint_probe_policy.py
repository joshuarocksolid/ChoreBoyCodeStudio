"""Unit tests for lint runtime-probe policy in MainWindow."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _build_window_stub() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._diagnostics_enabled = True
    window_any._diagnostics_realtime = True
    window_any._loaded_project = None
    window_any._editor_widgets_by_path = {}
    window_any._known_runtime_modules = None
    window_any._selected_linter = constants.LINTER_PROVIDER_DEFAULT
    window_any._lint_rule_overrides = {}
    window_any._stored_lint_diagnostics = {}
    window_any._intelligence_runtime_settings = SimpleNamespace(metrics_logging_enabled=False)
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: None)
    window_any._background_tasks = _FakeBackgroundTasks()
    window_any._workflow_broker = object()
    window_any._workspace_controller = SimpleNamespace(
        buffer_revision=lambda _path: 1,
        open_editor_paths=lambda: list(window_any._editor_widgets_by_path.keys()),
    )
    window_any._push_diagnostics_to_editor = lambda *_args, **_kwargs: None
    window_any._update_tab_diagnostic_indicator = lambda *_args, **_kwargs: None
    window_any._render_merged_problems_panel = lambda: None
    window_any._update_status_bar_diagnostics = lambda *_args, **_kwargs: None
    return window


def test_render_lint_manual_trigger_allows_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.main_window.analyze_python_with_workflow", _fake_analyze)

    MainWindow._render_lint_diagnostics_for_file(window, "/tmp/main.py", trigger="manual")
    background_call = window_any._background_tasks.calls[0]
    background_call["task"](threading.Event())

    assert captured == [True]


def test_render_lint_save_trigger_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.main_window.analyze_python_with_workflow", _fake_analyze)

    MainWindow._render_lint_diagnostics_for_file(window, "/tmp/main.py", trigger="save")
    background_call = window_any._background_tasks.calls[0]
    background_call["task"](threading.Event())

    assert captured == [False]


def test_lint_all_open_files_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    window_any._editor_widgets_by_path = {
        "/tmp/a.py": SimpleNamespace(toPlainText=lambda: "import x\n"),
        "/tmp/b.py": SimpleNamespace(toPlainText=lambda: "import y\n"),
    }
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.main_window.analyze_python_with_workflow", _fake_analyze)

    MainWindow._lint_all_open_files(window)
    assert len(window_any._background_tasks.calls) == 2
    for background_call in window_any._background_tasks.calls:
        background_call["task"](threading.Event())

    assert captured == [False, False]


def test_render_lint_drops_stale_results_for_changed_buffer() -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    editor_widget = SimpleNamespace(toPlainText=lambda: "print('a')\n")
    window_any._editor_widgets_by_path = {"/tmp/main.py": editor_widget}
    applied: list[tuple[str, list[object]]] = []
    revisions = {"current": 1}
    window_any._workspace_controller = SimpleNamespace(
        buffer_revision=lambda _path: revisions["current"],
        open_editor_paths=lambda: list(window_any._editor_widgets_by_path.keys()),
    )
    window_any._apply_lint_diagnostics_result = lambda file_path, diagnostics: applied.append((file_path, diagnostics))

    MainWindow._render_lint_diagnostics_for_file(window, "/tmp/main.py", trigger="save")
    background_call = window_any._background_tasks.calls[0]

    revisions["current"] = 2
    background_call["on_success"](["diagnostic"])

    assert applied == []
