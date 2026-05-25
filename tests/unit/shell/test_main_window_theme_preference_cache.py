"""Unit tests for MainWindow theme changes via ShellThemeWorkflow."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def _build_window_stub() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    theme_host = MagicMock()
    theme_host.is_applying_theme_styles = False
    theme_host.system_dark_theme_preference = True
    workflow = MagicMock()
    workflow.host = theme_host
    workflow.invalidate_system_dark_theme_preference = lambda: setattr(
        theme_host,
        "system_dark_theme_preference",
        None,
    )
    window_any._shell_theme_workflow = workflow
    window_any._theme_mode = "light"
    window_any._persist_theme_mode = lambda _mode: None
    window_any._quick_open_dialog = None
    window_any._sync_theme_menu_check_state = lambda: None
    window_any._logger = type("LoggerStub", (), {"info": lambda *_args, **_kwargs: None})()
    return window


def test_handle_set_theme_invalidates_cached_system_preference() -> None:
    window = _build_window_stub()

    MainWindow._handle_set_theme(window, "dark")

    assert window._theme_mode == "dark"
    assert window._shell_theme_workflow.host.system_dark_theme_preference is None
    window._shell_theme_workflow.apply_theme_styles.assert_called_once()
