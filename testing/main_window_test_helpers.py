"""Shared helpers for MainWindow integration and teardown tests."""

from __future__ import annotations

import time
from typing import Any, Callable

from app.shell.main_window import MainWindow


def ensure_shell_qapplication(monkeypatch: Any) -> Any:
    """Return an offscreen QApplication with QActionGroup compatibility shim."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    import PySide2.QtGui as qt_gui
    import PySide2.QtWidgets as qt_widgets

    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]

    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def stop_main_window_timers(window: MainWindow) -> None:
    """Stop composition polling timers so tests do not trigger async shell work."""
    composition_timers = getattr(window, "_composition_timers", None)
    if composition_timers is not None:
        composition_timers.stop_all()
        return

    window._auto_save_to_file_timer.stop()
    window._realtime_lint_timer.stop()
    window._project_tree_preview_click_timer.stop()
    window._run_event_timer.stop()
    window._repl_event_timer.stop()
    window._external_change_poll_timer.stop()
    window._restore_project_timer.stop()
    window._auto_start_repl_timer.stop()
    window._runtime_probe_timer.stop()
    window._startup_probe_refresh_timer.stop()


def apply_standard_main_window_test_patches(window: MainWindow) -> None:
    """Disable expensive background work that integration tests do not assert on."""
    window._intelligence_cache_workflow.start_symbol_indexing = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    if hasattr(window, "_shell_theme_workflow"):
        window._shell_theme_workflow.apply_theme_styles = lambda: None  # type: ignore[method-assign]


def prepare_main_window_for_test(
    window: MainWindow,
    *,
    app: Any | None = None,
) -> None:
    """Apply standard test patches and stop timers immediately after construction."""
    stop_main_window_timers(window)
    apply_standard_main_window_test_patches(window)
    if app is not None:
        app.processEvents()


def wait_for(
    predicate: Callable[[], bool],
    app: Any,
    *,
    timeout_seconds: float = 0.5,
) -> bool:
    """Poll ``predicate`` with ``processEvents`` until true or timeout."""
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()
