"""Helpers for disposing MainWindow instances in tests."""

from __future__ import annotations

from typing import Any

from app.shell.main_window import MainWindow
from app.shell.main_window_lifecycle import MainWindowLifecycle
from testing.runtime_child_reaper import reap_leaked_runtime_children


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
    reap_leaked_runtime_children()
    if app is not None:
        window.deleteLater()
        app.processEvents()
