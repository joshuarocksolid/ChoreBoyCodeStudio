# pyright: reportAttributeAccessIssue=false
"""Shared K24–K26 scripts. The lane tests and the together test both call these."""

from __future__ import annotations

from app.features.form_builder.qtside.canvas.layers.connections import drawable_steps
from app.qt.QtWidgets import QWidget
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb
from tests.form_builder.qtside.test_m6_2b_k26 import script_k26
from tests.form_builder.qtside.test_m6_m6_1b_k24 import script_k24

__all__ = ["script_k24", "script_k25", "script_k26"]


def _name(surface: object) -> str:
    document = surface.session.document  # type: ignore[attr-defined]
    current = surface.session.selection.state.current  # type: ignore[attr-defined]
    node = document.get(current) if current is not None else None
    return getattr(node, "object_name", "") or ""


def script_k25(kb: Kb) -> None:
    """K25 on the open sale form. Keys only. Restores the form bytes."""
    surface = kb.surface
    canvas = surface.workbench.canvas
    original = kb.text()
    kb.press("Key_F4")
    banner = canvas._banner
    label = banner.findChild(QWidget, "formBuilder.overlayBannerText")
    kb.check(banner.isVisible() and label is not None and bool(label.text()), "F4 shows the banner")
    for _ in range(16):
        if _name(surface) == "phoneEdit":
            break
        kb.press("Key_Tab")
    kb.check(_name(surface) == "phoneEdit", "Tab reached phoneEdit, have %s" % _name(surface))
    kb.press("Key_Return")
    kb.check(surface.modes.link_source == surface.session.document.by_name("phoneEdit")[0], "Enter arms phoneEdit")
    for _ in range(16):
        if _name(surface) == "nameEdit":
            break
        kb.press("Key_Tab")
    kb.check(_name(surface) == "nameEdit", "Tab reached nameEdit, have %s" % _name(surface))
    kb.press("Key_Return")
    kb.check(kb.focus_name() == "formBuilder.eventPickerSearch", "picker open, focus %s" % kb.focus_name())
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.press("Key_Return")
    phone = [
        step
        for step in drawable_steps(surface.session.document)
        if step.sender == "phoneEdit" and step.receiver == "nameEdit"
    ]
    kb.check(bool(phone) and phone[0].signal == "returnPressed()", "phoneEdit returnPressed reaches nameEdit")
    kb.press("Key_Escape")
    if surface.modes.active == "connections":
        kb.press("Key_Escape")
    kb.check(surface.modes.active == "", "Esc closed the overlay, have %s" % surface.modes.active)
    kb.press("Key_L", "Control", "Shift")
    status = surface.editor_status_sentence()
    kb.check(status == "Showing all 3 connections. Ctrl+Shift+L hides them.", status)
    while kb.session.log.can_undo():  # type: ignore[attr-defined]
        kb.press("Key_Z", "Control")
    kb.check(kb.text() == original, "undo restored the form")
    kb.press("Key_L", "Control", "Shift")
    kb.press("Key_F4")
    kb.press("Key_R", "Control")
    kb.type("saveButton")
    kb.press("Key_Return")
    kb.press("Key_Return")
    kb.press("Key_Home")
    kb.press("Key_Escape")
    kb.press("Key_Escape")
    kb.check(kb.text() == original, "Esc twice wrote nothing")
    kb.check(not kb.session.log.can_undo(), "no undo left")  # type: ignore[attr-defined]
