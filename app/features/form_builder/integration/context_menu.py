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
