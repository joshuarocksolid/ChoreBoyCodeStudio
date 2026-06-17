"""Helpers for disposing MainWindow instances in tests."""

from __future__ import annotations

import time
from typing import Any

from app.shell.main_window import MainWindow
from app.shell.main_window_lifecycle import MainWindowLifecycle
from testing.runtime_child_reaper import leaked_runtime_child_pids, reap_leaked_runtime_children

_SHUTDOWN_WAIT_SECONDS = 3.0


def shutdown_main_window_for_test(window: MainWindow, app: Any | None = None) -> None:
    """Mirror the shutdown side of closeEvent without QMessageBox prompts.

    Ensures background task executors, intelligence workers, and nested AppRun
    runtime children are stopped so non-daemon threads and subprocesses do not
    keep the interpreter alive.
    """
    window._is_shutting_down = True
    MainWindowLifecycle.begin_shutdown_teardown(window)
    MainWindowLifecycle.stop_active_run_before_close(window)
    if app is not None:
        app.processEvents()
    deadline = time.time() + _SHUTDOWN_WAIT_SECONDS
    while time.time() < deadline:
        if not leaked_runtime_child_pids():
            break
        if app is not None:
            app.processEvents()
        time.sleep(0.05)
    reap_leaked_runtime_children()
    if app is not None:
        window.deleteLater()
        app.processEvents()
