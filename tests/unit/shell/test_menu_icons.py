"""Smoke tests for main-menu icon coverage."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QMainWindow

from app.shell.menu_icons import all_static_menu_icon_action_ids, apply_menu_icons, build_menu_icon
from app.shell.menus import MenuCallbacks, build_menu_stubs
from app.shell.theme_tokens import ShellThemeTokens

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    return qapp


def _tokens(
    *,
    primary: str,
    muted: str,
    accent: str,
    is_dark: bool = False,
    is_high_contrast: bool = False,
) -> ShellThemeTokens:
    return ShellThemeTokens(
        window_bg="#000000" if is_dark else "#FFFFFF",
        panel_bg="#000000" if is_dark else "#FFFFFF",
        editor_bg="#000000" if is_dark else "#FFFFFF",
        text_primary=primary,
        text_muted=muted,
        border=primary,
        accent=accent,
        gutter_bg="#000000" if is_dark else "#FFFFFF",
        gutter_text=muted,
        line_highlight="#111111" if is_dark else "#EEEEEE",
        is_dark=is_dark,
        icon_primary=primary,
        icon_muted=muted,
        debug_paused_color="#F59E0B",
        debug_running_color="#16A34A",
        diag_error_color="#DC2626",
        diag_warning_color="#D97706",
        test_passed_color="#16A34A",
        is_high_contrast=is_high_contrast,
        focus_border_width=2 if is_high_contrast else 1,
    )


def test_every_static_main_menu_action_has_icon_mapping(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())

    assert sorted(set(registry.actions) - set(all_static_menu_icon_action_ids())) == []


@pytest.mark.parametrize(
    "tokens",
    [
        _tokens(primary="#1F2937", muted="#64748B", accent="#2563EB"),
        _tokens(primary="#E5E7EB", muted="#9CA3AF", accent="#60A5FA", is_dark=True),
        _tokens(primary="#000000", muted="#1F2937", accent="#0000EE", is_high_contrast=True),
        _tokens(
            primary="#FFFFFF",
            muted="#D1D5DB",
            accent="#66B2FF",
            is_dark=True,
            is_high_contrast=True,
        ),
    ],
)
def test_static_menu_icons_render_in_all_theme_modes(
    _ensure_qapp,  # type: ignore[no-untyped-def]
    tokens: ShellThemeTokens,
) -> None:
    for action_id in all_static_menu_icon_action_ids():
        icon = build_menu_icon(action_id, tokens)
        assert icon is not None, action_id
        assert not icon.pixmap(16, 16).isNull(), action_id


def test_apply_menu_icons_sets_submenu_icons(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())

    apply_menu_icons(
        registry,
        _tokens(primary="#1F2937", muted="#64748B", accent="#2563EB"),
    )

    open_recent_menu = registry.menu("shell.menu.file.openRecent")
    theme_menu = registry.menu("shell.menu.view.theme")
    assert open_recent_menu is not None
    assert theme_menu is not None
    assert not open_recent_menu.menuAction().icon().isNull()
    assert not theme_menu.menuAction().icon().isNull()
