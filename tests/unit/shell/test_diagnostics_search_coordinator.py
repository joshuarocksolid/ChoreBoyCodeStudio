"""Unit tests for diagnostics/search orchestration coordinators."""

from __future__ import annotations

import logging

import pytest

from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator, SearchResultsCoordinator

pytestmark = pytest.mark.unit


def test_schedule_realtime_lint_sets_pending_file_and_starts_timer() -> None:
    state: dict[str, object] = {"pending": None, "timer_started": False}
    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda file_path: state.__setitem__("pending", file_path),
        get_pending_realtime_file_path=lambda: state.get("pending"),  # type: ignore[return-value]
        start_realtime_timer=lambda: state.__setitem__("timer_started", True),
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda _file_path, _trigger: None,
        get_open_editor_paths=lambda: [],
        render_merged_problems_panel=lambda: None,
        set_known_runtime_modules=lambda _modules: None,
        run_background_task=lambda **_kwargs: None,
        state_root=lambda: None,
        logger=logging.getLogger("test"),
        show_runtime_probe_warning=lambda _message: None,
    )

    orchestrator.schedule_realtime_lint("/tmp/project/main.py")
    assert state["pending"] == "/tmp/project/main.py"
    assert state["timer_started"] is True

    state["pending"] = None
    state["timer_started"] = False
    orchestrator.schedule_realtime_lint("/tmp/project/README.md")
    assert state["pending"] is None
    assert state["timer_started"] is False


def test_run_scheduled_realtime_lint_requires_active_matching_tab() -> None:
    state: dict[str, object] = {"pending": "/tmp/project/main.py"}
    lint_calls: list[tuple[str, str]] = []
    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda file_path: state.__setitem__("pending", file_path),
        get_pending_realtime_file_path=lambda: state.get("pending"),  # type: ignore[return-value]
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: "/tmp/project/main.py",
        render_lint_for_file=lambda file_path, trigger: lint_calls.append((file_path, trigger)),
        get_open_editor_paths=lambda: [],
        render_merged_problems_panel=lambda: None,
        set_known_runtime_modules=lambda _modules: None,
        run_background_task=lambda **_kwargs: None,
        state_root=lambda: None,
        logger=logging.getLogger("test"),
        show_runtime_probe_warning=lambda _message: None,
    )

    orchestrator.run_scheduled_realtime_lint()

    assert state["pending"] is None
    assert lint_calls == [("/tmp/project/main.py", "realtime")]


def test_start_runtime_module_probe_success_sets_modules_and_relints(monkeypatch: pytest.MonkeyPatch) -> None:
    set_modules: list[frozenset[str]] = []
    lint_calls: list[tuple[str, str]] = []
    render_calls = {"count": 0}
    background_invocation: dict[str, object] = {}

    def _run_background_task(**kwargs):  # type: ignore[no-untyped-def]
        background_invocation.update(kwargs)

    orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: True,
        diagnostics_realtime=lambda: True,
        set_pending_realtime_file_path=lambda _file_path: None,
        get_pending_realtime_file_path=lambda: None,
        start_realtime_timer=lambda: None,
        get_active_tab_file_path=lambda: None,
        render_lint_for_file=lambda file_path, trigger: lint_calls.append((file_path, trigger)),
        get_open_editor_paths=lambda: ["/tmp/project/a.py", "/tmp/project/README.md"],
        render_merged_problems_panel=lambda: render_calls.__setitem__("count", render_calls["count"] + 1),
        set_known_runtime_modules=lambda modules: set_modules.append(modules),
        run_background_task=_run_background_task,
        state_root=lambda: None,
        logger=logging.getLogger("test"),
        show_runtime_probe_warning=lambda _message: None,
    )

    orchestrator.start_runtime_module_probe(user_initiated=True)
    on_success = background_invocation["on_success"]
    assert callable(on_success)
    on_success(frozenset({"FreeCAD", "Path"}))  # type: ignore[operator]

    assert set_modules == [frozenset({"FreeCAD", "Path"})]
    assert lint_calls == [("/tmp/project/a.py", "tab_change")]
    assert render_calls["count"] == 1


def test_search_results_coordinator_dispatches_update() -> None:
    updates: list[tuple[list[str], str]] = []
    dispatched: list[bool] = []

    coordinator = SearchResultsCoordinator(
        set_search_results=lambda matches, query: updates.append((matches, query)),  # type: ignore[arg-type]
        dispatch_to_main_thread=lambda callback: (dispatched.append(True), callback()),
    )

    coordinator.schedule_results_update(["result"], "needle")  # type: ignore[arg-type]

    assert dispatched == [True]
    assert updates == [(["result"], "needle")]
