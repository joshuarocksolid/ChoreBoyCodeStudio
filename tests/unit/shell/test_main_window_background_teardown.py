"""Regression tests for MainWindow background executor teardown in tests."""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.shell.main_window import MainWindow
from app.shell.main_window_lifecycle import MainWindowLifecycle
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.runtime_child_reaper import leaked_runtime_child_pids
from testing.main_window_test_helpers import prepare_main_window_for_test

pytestmark = pytest.mark.unit

_THREAD_JOIN_TIMEOUT_SECONDS = 0.5
_TASK_COMPLETION_TIMEOUT_SECONDS = 0.5


def _shell_task_thread_count() -> int:
    return sum(1 for t in threading.enumerate() if t.name.startswith("shell-task"))


def _wait_until(predicate, *, timeout_seconds: float, app: QApplication | None = None) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    if app is not None:
        app.processEvents()
    return predicate()


@pytest.fixture
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_shutdown_main_window_for_test_returns_executor_threads_to_baseline(
    tmp_path,
    _qapp: QApplication,
) -> None:
    """After scheduling work, teardown should shut down shell TaskPool workers."""
    baseline = _shell_task_thread_count()
    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        done: list[bool] = []
        window._background_tasks.run(
            key="noop",
            task=lambda _cancel: None,
            on_success=lambda _r: done.append(True),
        )
        assert _wait_until(lambda: bool(done), timeout_seconds=_TASK_COMPLETION_TIMEOUT_SECONDS, app=_qapp)
        assert done == [True]
        assert _shell_task_thread_count() > baseline
    finally:
        shutdown_main_window_for_test(window)

    assert _wait_until(
        lambda: _shell_task_thread_count() == baseline,
        timeout_seconds=_THREAD_JOIN_TIMEOUT_SECONDS,
    )
    assert _shell_task_thread_count() == baseline


def test_shutdown_main_window_for_test_invokes_full_close_teardown_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test helper should mirror closeEvent teardown order."""
    calls: list[str] = []
    monkeypatch.setattr(
        MainWindowLifecycle,
        "begin_shutdown_teardown",
        lambda window: calls.append("begin"),
    )
    monkeypatch.setattr(
        MainWindowLifecycle,
        "stop_active_run_before_close",
        lambda window: calls.append("stop"),
    )
    window = MainWindow.__new__(MainWindow)
    window_any = window
    window_any._is_shutting_down = False  # type: ignore[attr-defined]

    shutdown_main_window_for_test(window)

    assert window_any._is_shutting_down is True  # type: ignore[attr-defined]
    assert calls == ["begin", "stop"]


def test_shutdown_main_window_for_test_leaves_no_runtime_child_descendants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    _qapp: QApplication,
) -> None:
    monkeypatch.setenv("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=_qapp)
    try:
        _qapp.processEvents()
    finally:
        shutdown_main_window_for_test(window, _qapp)

    assert leaked_runtime_child_pids() == []
