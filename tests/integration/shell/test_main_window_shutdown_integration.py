"""Integration tests for main-window shutdown behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QCloseEvent
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_close_event_stops_active_run_before_accepting_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(tmp_path.resolve()))

    stop_calls: list[str] = []
    clear_mode_calls: list[str] = []
    console_session_updates: list[bool] = []

    monkeypatch.setattr(window, "_confirm_proceed_with_unsaved_changes", lambda _action: True)
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
    monkeypatch.setattr(window._run_service, "stop_run", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(
        window._run_session_controller,
        "clear_active_session_mode",
        lambda: clear_mode_calls.append("cleared"),
    )
    assert window._python_console_widget is not None
    monkeypatch.setattr(
        window._python_console_widget,
        "set_session_active",
        lambda active: console_session_updates.append(active),
    )

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert stop_calls == ["stop"]
    assert clear_mode_calls == ["cleared"]
    assert console_session_updates == [False]
