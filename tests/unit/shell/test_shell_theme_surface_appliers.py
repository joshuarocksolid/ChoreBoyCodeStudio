"""Tests for shell theme surface application and callback rebinding."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs
from app.shell.shell_theme_surface_appliers import (
    ShellThemeSurfaceRefs,
    apply_menu_bar_icons,
    build_main_window_shell_theme_callbacks,
)
from app.shell.theme_tokens import ShellThemeTokens

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    return qapp


def _theme_tokens() -> ShellThemeTokens:
    return ShellThemeTokens(
        window_bg="#FFFFFF",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#1F2937",
        text_muted="#64748B",
        border="#1F2937",
        accent="#2563EB",
        gutter_bg="#FFFFFF",
        gutter_text="#64748B",
        line_highlight="#EEEEEE",
        is_dark=False,
        icon_primary="#1F2937",
        icon_muted="#64748B",
    )


def _attach_theme_surface_attrs(window: QMainWindow) -> None:
    window._editor_manager = None
    window._editor_widgets_by_path = {}
    window._tab_content_registry = None
    window._python_console_widget = None
    window._run_log_panel = None
    window._search_sidebar = None
    window._activity_bar = None
    window._test_explorer_panel = None
    window._outline_panel = None
    window._problems_panel = None


def test_stale_menu_registry_callbacks_skip_menu_icons(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _attach_theme_surface_attrs(window)
    window._menu_registry = None

    callbacks = build_main_window_shell_theme_callbacks(window)
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())
    window._menu_registry = registry

    tokens = _theme_tokens()
    callbacks.apply_menu_bar_icons(tokens)

    save_action = registry.action("shell.action.file.save")
    assert save_action is not None
    assert save_action.icon().isNull()


def test_refresh_surface_refs_rebinds_menu_registry_for_icons(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _attach_theme_surface_attrs(window)
    window._menu_registry = None

    build_main_window_shell_theme_callbacks(window)
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())
    window._menu_registry = registry

    refreshed_callbacks = build_main_window_shell_theme_callbacks(window)
    refreshed_callbacks.apply_menu_bar_icons(_theme_tokens())

    save_action = registry.action("shell.action.file.save")
    assert save_action is not None
    assert not save_action.icon().isNull()


def test_apply_menu_bar_icons_delegates_to_apply_menu_icons(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())
    refs = ShellThemeSurfaceRefs(
        editor_manager=None,
        editor_widgets_by_path={},
        tab_content_registry=None,
        python_console_widget=None,
        run_log_panel=None,
        search_sidebar=None,
        activity_bar=None,
        menu_registry=registry,
        test_explorer_panel=None,
        outline_panel=None,
        problems_panel=None,
        shell_style_setter=window.setStyleSheet,
    )

    apply_menu_bar_icons(refs, _theme_tokens())

    run_action = registry.action("shell.action.run.run")
    assert run_action is not None
    assert not run_action.icon().isNull()
