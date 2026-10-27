"""The canvas and outline context menu (UX-WRAP-006, UX-WRAP-007, UX-WRAP-009, R3-56)."""

from __future__ import annotations

from typing import Callable

from app.qt.QtWidgets import QMenu

from app.features.form_builder.engine.layout_actions import (
    LOCKS,
    ChangeTo,
    KeepContent,
    LockSize,
    OfferSheet,
    RemoveLayout,
    gate,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome, menu_style


def paint_menu(menu: QMenu, chrome: FormChrome) -> None:
    """Paint ``menu`` and every submenu from ``chrome``. Submenus do not inherit a sheet."""
    sheet = menu_style(chrome)
    menu.setStyleSheet(sheet)
    for child in menu.findChildren(QMenu):
        child.setStyleSheet(sheet)


_CLIPBOARD_ROWS = (
    ("Copy", "form.action.copy"),
    ("Cut", "form.action.cut"),
    ("Paste", "form.action.paste"),
    ("Duplicate", "form.action.duplicate"),
    ("Delete", "form.action.delete"),
    ("Select all", "form.action.selectAll"),
    ("Save to pieces", "form.action.savePiece"),
)


def add_clipboard_actions(menu: QMenu, dispatch: Callable[[str], None]) -> None:
    """Copy through Save to pieces. Each row calls ``dispatch`` with its command id."""
    for label, command_id in _CLIPBOARD_ROWS:
        action = menu.addAction(label)
        action.triggered.connect(lambda _checked=False, command_id=command_id: dispatch(command_id))
    menu.addSeparator()


def fill_context_menu(menu: QMenu, sheet: OfferSheet, run: Callable[[object], None]) -> None:
    """Change to, Remove layout, Keep at content size, and Size constraints.

    Change to is left out when the selection has no related class. A row
    that cannot apply stays visible, disabled, with the reason as its tooltip.
    """
    menu.setToolTipsVisible(True)
    if sheet.morphs:
        change = menu.addMenu("Change to")
        change.setToolTipsVisible(True)
        for target in sheet.morphs:
            _add(change, target.label, sheet, ChangeTo(target.class_name), run)
    _add(menu, "Remove layout\u2026", sheet, RemoveLayout(), run)
    _add(menu, "Keep at content size", sheet, KeepContent(), run)
    sizes = menu.addMenu("Size constraints")
    sizes.setToolTipsVisible(True)
    for which, label in LOCKS:
        _add(sizes, label, sheet, LockSize(which), run)


def _add(menu: QMenu, label: str, sheet: OfferSheet, request: object, run: Callable[[object], None]) -> None:
    offer = gate(sheet, request)
    action = menu.addAction(label)
    action.setEnabled(offer.enabled)
    if offer.reason:
        action.setToolTip(offer.reason)
    action.triggered.connect(lambda _checked=False, request=request: run(request))
