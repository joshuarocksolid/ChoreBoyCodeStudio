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

pytestmark = pytest.mark.unit


def _shell_task_thread_count() -> int:
    return sum(1 for t in threading.enumerate() if t.name.startswith("shell-task"))


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
        deadline = time.time() + 3.0
        while time.time() < deadline and not done:
            _qapp.processEvents()
            time.sleep(0.02)
        assert done == [True]
        assert _shell_task_thread_count() > baseline
    finally:
        shutdown_main_window_for_test(window)

    deadline = time.time() + 3.0
    while time.time() < deadline and _shell_task_thread_count() > baseline:
        time.sleep(0.05)

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
    try:
        _qapp.processEvents()
    finally:
        shutdown_main_window_for_test(window, _qapp)

    assert leaked_runtime_child_pids() == []
