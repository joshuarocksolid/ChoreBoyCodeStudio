"""Unit tests for run/debug presenter failure mapping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.run_debug_presenter import RunDebugPresenter  # noqa: E402
from app.shell.run_session_controller import RunSessionStartFailureReason, RunSessionStartResult  # noqa: E402

pytestmark = pytest.mark.unit


class _FailingRunSessionController:
    def __init__(self, result: RunSessionStartResult) -> None:
        self._result = result

    def start_session(self, **_kwargs: object) -> RunSessionStartResult:
        return self._result


def _make_presenter_window(result: RunSessionStartResult) -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FailingRunSessionController(result)
    window_any._debug_panel = None
    window_any._save_workflow = SimpleNamespace(handle_save_all_action=lambda: True)
    window_any._prepare_for_session_start = lambda: None
    window_any._append_console_line = lambda _text, _stream="stdout": None
    window_any._append_python_console_line = lambda _text, _stream="stdout": None
    window_any._refresh_run_action_states = lambda: None
    window_any._auto_open_console_on_run_output = False
    window_any._set_run_status = lambda _status: None
    return window


def test_start_session_already_running_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _make_presenter_window(
        RunSessionStartResult(
            started=False,
            failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
            error_message="Stop the current run first.",
        )
    )
    presenter = RunDebugPresenter(window)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = presenter.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [("Run already in progress", "Stop the current run first.")]
