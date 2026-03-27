"""Unit tests for MainWindow system-theme preference caching."""

from __future__ import annotations

import subprocess
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def _build_window_stub() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._system_dark_theme_preference = None
    window_any._theme_mode = "system"
    window_any._persist_theme_mode = lambda _mode: None
    window_any._quick_open_dialog = None
    window_any._apply_theme_styles = lambda: None
    window_any._sync_theme_menu_check_state = lambda: None
    window_any._logger = type("LoggerStub", (), {"info": lambda *_args, **_kwargs: None})()
    return window


def test_system_prefers_dark_theme_uses_cached_value(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="'prefer-dark'\n", stderr="")

    monkeypatch.setattr("app.shell.main_window.subprocess.run", fake_run)

    assert MainWindow._system_prefers_dark_theme(window) is True
    assert MainWindow._system_prefers_dark_theme(window) is True
    assert len(calls) == 1


def test_system_prefers_dark_theme_handles_subprocess_error(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()

    def fake_run(command: list[str], **_kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("app.shell.main_window.subprocess.run", fake_run)

    assert MainWindow._system_prefers_dark_theme(window) is False
    assert window._system_dark_theme_preference is False


def test_handle_set_theme_invalidates_cached_system_preference() -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    window_any._theme_mode = "light"
    window_any._system_dark_theme_preference = True

    MainWindow._handle_set_theme(window, "dark")

    assert window._theme_mode == "dark"
    assert window._system_dark_theme_preference is None
