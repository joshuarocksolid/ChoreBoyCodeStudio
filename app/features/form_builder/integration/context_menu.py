"""The canvas and outline context menu (UX-WRAP-006, UX-WRAP-007, UX-WRAP-009, R3-56)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.qt.QtWidgets import QMenu

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import (
    LOCKS,
    ChangeTo,
    KeepContent,
    LockSize,
    OfferSheet,
    RemoveLayout,
    gate,
)
from app.features.form_builder.integration.menu_ext import FIRST, LAST, STRUCTURE, MenuContext, MenuRegistry
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.theme.chrome import FormChrome, menu_style


def paint_menu(menu: QMenu, chrome: FormChrome) -> None:
    """Paint ``menu`` and every submenu from ``chrome``. Submenus do not inherit a sheet."""
    sheet = menu_style(chrome)
    menu.setStyleSheet(sheet)
    for child in menu.findChildren(QMenu):
        child.setStyleSheet(sheet)


_CLIPBOARD_ROWS = (
    ("Copy", "form.action.copy", "Ctrl+C"),
    ("Cut", "form.action.cut", "Ctrl+X"),
    ("Paste", "form.action.paste", "Ctrl+V"),
    ("Duplicate", "form.action.duplicate", "Ctrl+D"),
    ("Delete", "form.action.delete", "Delete"),
    ("Select all", "form.action.selectAll", ""),
    ("Save to pieces", "form.action.savePiece", ""),
)


def add_clipboard_actions(
    menu: QMenu,
    dispatch: Callable[[str], None],
    enabled: Optional[Callable[[str], bool]] = None,
) -> None:
    """Copy through Save to pieces. Each row calls ``dispatch`` with its command id.

    ``enabled`` decides which rows can act. A missing callback leaves every row on.
    """
    menu.setToolTipsVisible(True)
    for label, command_id, shortcut in _CLIPBOARD_ROWS:
        text = "%s\t%s" % (label, shortcut) if shortcut else label
        action = menu.addAction(text)
        if enabled is not None:
            action.setEnabled(enabled(command_id))
        if shortcut:
            action.setToolTip(shortcut)
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


def build_context_menu(
    menu: QMenu,
    *,
    contributors: MenuRegistry,
    ids: Tuple[NodeId, ...],
    current: Optional[NodeId],
    session: FormSession,
    dispatch: Callable[[str], None],
    enabled: Optional[Callable[[str], bool]],
    sheet: OfferSheet,
    run: Callable[[object], None],
) -> None:
    """The whole menu, in order: first, clipboard, structure, layout rows, last.

    Each contributor group is followed by a separator only when it added a row.
    """
    context = MenuContext(menu=menu, ids=ids, current=current, session=session, dispatch=dispatch)
    _run_group(menu, contributors, FIRST, context)
    add_clipboard_actions(menu, dispatch, enabled)
    _run_group(menu, contributors, STRUCTURE, context)
    fill_context_menu(menu, sheet, run)
    _run_group(menu, contributors, LAST, context, leading_separator=True)


def _run_group(
    menu: QMenu,
    contributors: MenuRegistry,
    group: str,
    context: MenuContext,
    *,
    leading_separator: bool = False,
) -> None:
    before = len(menu.actions())
    contributors.run(group, context)
    if len(menu.actions()) == before:
        return
    if not leading_separator:
        menu.addSeparator()
    elif before:
        menu.insertSeparator(menu.actions()[before])


def _add(menu: QMenu, label: str, sheet: OfferSheet, request: object, run: Callable[[object], None]) -> None:
    offer = gate(sheet, request)
    action = menu.addAction(label)
    action.setEnabled(offer.enabled)
    if offer.reason:
        action.setToolTip(offer.reason)
    action.triggered.connect(lambda _checked=False, request=request: run(request))
