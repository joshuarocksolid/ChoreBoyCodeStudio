"""Unit tests for re-linting open files after runtime module probe completes."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator

pytestmark = pytest.mark.unit


def _make_orchestrator(
    *,
    open_paths: list[str],
) -> tuple[DiagnosticsOrchestrator, list[str], list[bool]]:
    relinted: list[str] = []
    merged: list[bool] = []

    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda _path: None,
        get_pending_realtime_file_path=lambda: None,
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda file_path, trigger: relinted.append(f"{file_path}:{trigger}"),
        get_open_editor_paths=lambda: list(open_paths),
        render_merged_problems_panel=lambda: merged.append(True),
        set_known_runtime_modules=lambda _modules: None,
        run_background_task=lambda **_kwargs: None,
        state_root=lambda: None,
        logger=logging.getLogger("test.runtime_probe_relint"),
        show_runtime_probe_warning=lambda _message: None,
    )
    return orchestrator, relinted, merged


def test_relint_open_python_files_lints_all_py_files() -> None:
    orchestrator, relinted, merged = _make_orchestrator(
        open_paths=[
            "/project/main.py",
            "/project/utils.py",
            "/project/README.md",
        ]
    )

    orchestrator.relint_open_python_files()

    assert sorted(relinted) == [
        "/project/main.py:tab_change",
        "/project/utils.py:tab_change",
    ]
    assert merged == [True]


def test_relint_open_python_files_skips_non_py() -> None:
    orchestrator, relinted, merged = _make_orchestrator(
        open_paths=[
            "/project/config.json",
            "/project/notes.txt",
        ]
    )

    orchestrator.relint_open_python_files()

    assert relinted == []
    assert merged == [True]


def test_relint_open_python_files_handles_empty_editor_set() -> None:
    orchestrator, relinted, merged = _make_orchestrator(open_paths=[])

    orchestrator.relint_open_python_files()

    assert relinted == []
    assert merged == [True]


def test_probe_on_success_triggers_relint() -> None:
    relint_calls: list[bool] = []
    known_modules: list[frozenset[str]] = []
    captured: dict[str, Any] = {}

    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda _path: None,
        get_pending_realtime_file_path=lambda: None,
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda *_args, **_kwargs: None,
        get_open_editor_paths=lambda: [],
        render_merged_problems_panel=lambda: None,
        set_known_runtime_modules=lambda modules: known_modules.append(modules),
        run_background_task=lambda *, key, task, on_success, on_error: captured.update(
            {"key": key, "task": task, "on_success": on_success, "on_error": on_error}
        ),
        state_root=lambda: None,
        logger=logging.getLogger("test.runtime_probe_relint"),
        show_runtime_probe_warning=lambda _message: None,
    )
    orchestrator.relint_open_python_files = lambda: relint_calls.append(True)  # type: ignore[method-assign]

    orchestrator.start_runtime_module_probe()

    assert captured["key"] == "runtime_module_probe"
    modules = frozenset(["os", "sys", "json"])
    captured["on_success"](modules)

    assert known_modules == [modules]
    assert relint_calls == [True]


def test_probe_on_success_empty_modules_logs_warning_and_skips_relint(caplog: pytest.LogCaptureFixture) -> None:
    relint_calls: list[bool] = []
    captured: dict[str, Any] = {}

    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda _path: None,
        get_pending_realtime_file_path=lambda: None,
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda *_args, **_kwargs: None,
        get_open_editor_paths=lambda: [],
        render_merged_problems_panel=lambda: None,
        set_known_runtime_modules=lambda _modules: None,
        run_background_task=lambda *, key, task, on_success, on_error: captured.update(
            {"on_success": on_success}
        ),
        state_root=lambda: None,
        logger=logging.getLogger("test.runtime_probe_relint"),
        show_runtime_probe_warning=lambda _message: None,
    )
    orchestrator.relint_open_python_files = lambda: relint_calls.append(True)  # type: ignore[method-assign]

    orchestrator.start_runtime_module_probe()
    with caplog.at_level(logging.WARNING):
        captured["on_success"](frozenset())

    assert relint_calls == []
    assert "empty module set" in caplog.text.lower()


def test_probe_on_success_empty_modules_user_initiated_shows_warning() -> None:
    shown_messages: list[str] = []
    captured: dict[str, Any] = {}

    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda _path: None,
        get_pending_realtime_file_path=lambda: None,
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda *_args, **_kwargs: None,
        get_open_editor_paths=lambda: [],
        render_merged_problems_panel=lambda: None,
        set_known_runtime_modules=lambda _modules: None,
        run_background_task=lambda *, key, task, on_success, on_error: captured.update(
            {"on_success": on_success}
        ),
        state_root=lambda: None,
        logger=logging.getLogger("test.runtime_probe_relint"),
        show_runtime_probe_warning=lambda message: shown_messages.append(message),
    )

    orchestrator.start_runtime_module_probe(user_initiated=True)
    captured["on_success"](frozenset())

    assert shown_messages
