"""Regression tests for MainWindow background executor teardown in tests."""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test

pytestmark = pytest.mark.unit


def _shell_task_thread_count() -> int:
    return sum(1 for t in threading.enumerate() if t.name.startswith("shell-task"))


@pytest.fixture
def _qapp() -> QApplication:  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


def test_shutdown_main_window_for_test_invokes_full_close_teardown_sequence() -> None:
    """Test helper should mirror closeEvent teardown order."""
    window = MainWindow.__new__(MainWindow)
    window_any = window
    calls: list[str] = []
    window_any._begin_shutdown_teardown = lambda: calls.append("begin")  # type: ignore[attr-defined]
    window_any._stop_active_run_before_close = lambda: calls.append("stop")  # type: ignore[attr-defined]
    window_any._is_shutting_down = False  # type: ignore[attr-defined]

    shutdown_main_window_for_test(window)

    assert window_any._is_shutting_down is True  # type: ignore[attr-defined]
    assert calls == ["begin", "stop"]
