"""Form > Preview, Preview options > Style and Screen, View Python code, Save image…, Print… (M5.5a, UX-M5-010).

The Aa menu is where the style and screens are picked with their caption
(UX-PREV-001); the Form menu offers the same choices for the keyboard, with the
check mark on the current one. The user's own screens join the Screen submenu each
time the Form menu opens. Print… is absent where Qt print support is missing.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Tuple

from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.integration.preview_options import ADD_SCREEN, BUILT_IN, DEFAULT_STYLE, style_label

logger = logging.getLogger(__name__)

PREVIEW_ID = "form.action.preview"
VIEW_CODE_ID = "form.action.viewCode"
SAVE_IMAGE_ID = "form.action.saveImage"
PRINT_ID = "form.action.printImage"
STYLE_PREFIX = "form.action.previewStyle."
SCREEN_PREFIX = "form.action.previewScreen."
ADD_SCREEN_ID = "form.action.previewScreenAdd"
USER_ID = "form.action.previewScreenUser."

_OPTIONS = "Preview options"


def _control(surface: Any) -> Any:
    return getattr(surface, "preview_control", None)


def _with_control(surface: Any) -> bool:
    return surface is not None and _control(surface) is not None


def _preview(surface: Any) -> None:
    surface.preview_form()


def _style_names() -> Tuple[str, ...]:
    from app.features.form_builder.integration.preview_options import ordered_styles
    from app.qt.QtWidgets import QStyleFactory

    return ordered_styles(str(name) for name in QStyleFactory.keys())


def _style_item(name: str, rank: int) -> FormMenuItem:
    def run(surface: Any) -> None:
        control = _control(surface)
        if control is not None:
            control.set_style(name)

    return FormMenuItem(
        STYLE_PREFIX + name,
        (_OPTIONS, "Style", style_label(name)),
        run,
        rank=1000 + rank,
        offered=lambda surface, shown=name: _sync_checks(surface, "style", shown),
    )


def _screen_item(profile: Any, rank: int) -> FormMenuItem:
    def run(surface: Any) -> None:
        control = _control(surface)
        if control is not None:
            control.set_screen(profile.name)

    return FormMenuItem(
        SCREEN_PREFIX + profile.name,
        (_OPTIONS, "Screen", profile.label),
        run,
        rank=1100 + rank,
        offered=lambda surface, shown=profile.name: _sync_checks(surface, "screen", shown),
    )


def _add_screen(surface: Any) -> None:
    control = _control(surface)
    if control is not None:
        control.add_screen_dialog()


def _view_code(surface: Any) -> None:
    surface.toggle_code_view()


def _save_image(surface: Any) -> None:
    surface.save_image()


def _print(surface: Any) -> None:
    surface.print_image()


def _print_offered(surface: Any) -> bool:
    from app.features.form_builder.integration.image_export import print_available

    return surface is not None and print_available()


_stamp: dict = {}


def _sync_checks(surface: Any, kind: str, name: str) -> bool:
    """Called when the Form menu opens, for each Style and Screen row: mark the current choice.

    The user's own screens are added to the Screen submenu in the same pass (once per opening).
    """
    control = _control(surface)
    if control is None:
        return False
    try:
        window = surface.window()
        now = time.monotonic()
        if now - _stamp.get(id(window), 0.0) > 0.05:
            _stamp[id(window)] = now
            _refresh_user_screens(window, control)
        _mark(window, control, kind, name)
    except Exception:
        logger.exception("the preview options could not be marked")
    return True


def _mark(window: Any, control: Any, kind: str, name: str) -> None:
    from app.qt.QtGui import QAction

    prefix = STYLE_PREFIX if kind == "style" else SCREEN_PREFIX
    action = window.findChild(QAction, prefix + name)
    if action is None:
        return
    chosen = control.choices.style if kind == "style" else control.current_profile().name
    action.setCheckable(True)
    action.setChecked(chosen.lower() == name.lower())


def _refresh_user_screens(window: Any, control: Any) -> None:
    """Replace the user's screens in Form > Preview options > Screen with the current list."""
    from app.qt.QtGui import QAction
    from app.qt.QtWidgets import QMenu

    menu = window.findChild(QMenu, "formBuilder.menu.Screen")
    if menu is None:
        return
    for action in list(menu.actions()):
        if action.objectName().startswith(USER_ID):
            menu.removeAction(action)
            action.deleteLater()
    add_action = window.findChild(QAction, ADD_SCREEN_ID)
    chosen = control.current_profile().name
    for profile in control.user_profiles():
        action = QAction(profile.label, menu)
        action.setObjectName(USER_ID + profile.name)
        action.setCheckable(True)
        action.setChecked(profile.name == chosen)
        action.triggered.connect(lambda _checked=False, value=profile.name: control.set_screen(value))
        if add_action is not None:
            menu.insertAction(add_action, action)
        else:
            menu.addAction(action)


def register(registry: Any) -> None:
    add: Callable[[FormMenuItem], None] = registry.add
    add(FormMenuItem(PREVIEW_ID, ("Preview",), _preview, hint="Ctrl+Shift+R", enabled=_with_control))
    for rank, name in enumerate(_style_names()):
        add(_style_item(name, rank))
    for rank, profile in enumerate(BUILT_IN):
        add(_screen_item(profile, rank))
    add(FormMenuItem(ADD_SCREEN_ID, (_OPTIONS, "Screen", ADD_SCREEN), _add_screen, rank=1150, enabled=_with_control))
    add(FormMenuItem(VIEW_CODE_ID, ("View Python code",), _view_code))
    add(FormMenuItem(SAVE_IMAGE_ID, ("Save image…",), _save_image))
    add(FormMenuItem(PRINT_ID, ("Print…",), _print, offered=_print_offered))
