"""Helpers for disposing MainWindow instances in tests."""

from __future__ import annotations

from typing import Any

from app.qt.qt_compat import delete_now
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
    # The first shutdown only cancels. Join before delete_now so a probe
    # thread is not still inside the window when Qt destroys it.
    tasks = getattr(window, "_background_tasks", None)
    join = getattr(tasks, "shutdown", None)
    if callable(join):
        join(wait=True)
    if app is not None:
        app.processEvents()
    reap_leaked_runtime_children()
    # deleteLater leaves the C++ window alive while a Python cycle holds the
    # wrapper, so the next test's application stylesheet restyles every previous
    # window. Destroy it now.
    delete_now(window)
