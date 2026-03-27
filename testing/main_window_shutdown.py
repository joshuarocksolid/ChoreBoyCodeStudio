"""Helpers for disposing MainWindow instances in tests."""

from __future__ import annotations

from app.shell.main_window import MainWindow


def shutdown_main_window_for_test(window: MainWindow) -> None:
    """Mirror the shutdown side of closeEvent without QMessageBox prompts.

    Ensures background task executors and intelligence workers are stopped so
    non-daemon ThreadPoolExecutor threads do not keep the interpreter alive.
    """
    window._is_shutting_down = True
    window._begin_shutdown_teardown()
    window._stop_active_run_before_close()
