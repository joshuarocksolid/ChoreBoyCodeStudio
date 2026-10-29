"""Keys of the editing modes (M5.6, UX-OVL-001, UX-MODE-001 .. 007).

F8 and F7 toggle the Tab order and Buddies overlays, F3 leaves one, F4 says where
Connections are until M6, F1 opens the help card of the selected widget. Enter,
Shift+Enter and Backspace in the Tab order overlay and Enter in the Buddies
overlay are handled by the canvas while an overlay is open; they are listed here
(``kind="qt"``) so Form designer keys shows them and the collision test sees them.
"""

from __future__ import annotations

from typing import Any

_FORM = ("form_tab",)
_WIDGETS = ("canvas", "outline", "inspector")
TAB_OVERLAY = "tab_order_overlay"
BUDDY_OVERLAY = "buddy_overlay"


def _tab_order(surface: Any) -> None:
    surface.toggle_overlay("tab_order")


def _buddies(surface: Any) -> None:
    surface.toggle_overlay("buddies")


def _leave(surface: Any) -> None:
    surface.leave_overlay()


def _connections(surface: Any) -> None:
    surface.about_connections()


def _help(surface: Any) -> None:
    surface.show_widget_help()


def register(keys: Any) -> None:
    keys.key("form.action.tabOrder", "Tab order overlay", "F8", _FORM, run=_tab_order)
    keys.key("form.action.buddies", "Buddies overlay", "F7", _FORM, run=_buddies)
    keys.key("form.action.leaveOverlay", "Leave overlay", "F3", _FORM, run=_leave)
    keys.key("form.action.connections", "Connections", "F4", _FORM, run=_connections)
    keys.key("form.action.widgetHelp", "Help card for the selected widget", "F1", _WIDGETS, run=_help)
    keys.key("form.action.tabOrderNumber", "Give the selected widget the next number", "Enter", (TAB_OVERLAY,), kind="qt", available=True)
    keys.key("form.action.tabOrderContinue", "Continue numbering from the selected widget", "Shift+Enter", (TAB_OVERLAY,), kind="qt", available=True)
    keys.key("form.action.tabOrderTakeBack", "Take back the last number", "Backspace", (TAB_OVERLAY,), kind="qt", available=True)
    keys.key("form.action.buddyLink", "Start or finish a buddy link", "Enter", (BUDDY_OVERLAY,), kind="qt", available=True)
