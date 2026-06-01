"""Unit tests for shell theme changes via ShellPreferencesRuntime."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.shell_preferences_runtime import ShellPreferencesRuntime

pytestmark = pytest.mark.unit


def _build_preferences_stub() -> tuple[ShellPreferencesRuntime, SimpleNamespace, MagicMock]:
    theme_workflow = MagicMock()
    theme_host = MagicMock()
    theme_host.is_applying_theme_styles = False
    theme_host.system_dark_theme_preference = True
    theme_workflow.host = theme_host
    theme_workflow.invalidate_system_dark_theme_preference = lambda: setattr(
        theme_host,
        "system_dark_theme_preference",
        None,
    )

    host = SimpleNamespace(
        _theme_mode="light",
        _quick_open_dialog=None,
        menu_registry=lambda: None,
    )
    host.theme_mode = lambda: host._theme_mode
    host.set_theme_mode = lambda mode: setattr(host, "_theme_mode", mode)
    host.shell_theme_workflow = lambda: theme_workflow
    host.quick_open_dialog = lambda: host._quick_open_dialog
    host.set_quick_open_dialog = lambda dialog: setattr(host, "_quick_open_dialog", dialog)
    host.logger = lambda: SimpleNamespace(info=lambda *_args, **_kwargs: None)
    host.settings_service = lambda: SimpleNamespace(update_global=lambda _fn: None)

    return ShellPreferencesRuntime(host), host, theme_workflow  # type: ignore[arg-type]


def test_handle_set_theme_invalidates_cached_system_preference() -> None:
    preferences, host, theme_workflow = _build_preferences_stub()

    preferences.handle_set_theme("dark")

    assert host._theme_mode == "dark"
    assert theme_workflow.host.system_dark_theme_preference is None
    theme_workflow.apply_theme_styles.assert_called_once()
