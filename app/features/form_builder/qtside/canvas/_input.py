"""Qt event to core event. Private to the canvas controller."""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Tuple

from app.qt.QtCore import QEvent, Qt
from app.qt.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from app.qt.QtWidgets import QGraphicsView
from app.qt.qt_compat import enum_value, event_pos

from app.features.form_builder.qtside.canvas.core.gesture import (
    Button,
    Event,
    Focus,
    Key,
    KeyName,
    KeyUp,
    Leave,
    Mods,
    Move,
    Press,
    Probe,
    Release,
    Wheel,
)
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, PortPoint

_FRAME_REQUEST: Optional[int] = None


def frame_request() -> QEvent:
    """One posted event. Registered after QApplication exists."""
    kind = _frame_type()
    type_enum = getattr(QEvent, "Type", None)
    if type_enum is not None:
        return QEvent(type_enum(kind))
    return QEvent(kind)


def is_frame_request(event: QEvent) -> bool:
    return enum_value(event.type()) == _frame_type()


def is_resize(event: QEvent) -> bool:
    return _is(event, "Resize")


def translate(event: QEvent, view: QGraphicsView, first_focus: bool) -> Optional[Event]:
    """None for events the canvas does not handle.

    Mouse positions become ``at`` (``view.mapToScene``, integral because the
    view transform is identity) and ``port``. A double click is a press with
    ``double`` set. Ctrl+=, Ctrl++, Ctrl+-, Ctrl+0 and Ctrl+9 are the zoom
    keys the shell also binds. Auto-repeat Space is dropped.
    """
    if _is(event, "MouseButtonPress") and isinstance(event, QMouseEvent):
        return _press(event, view, False)
    if _is(event, "MouseButtonDblClick") and isinstance(event, QMouseEvent):
        return _press(event, view, True)
    if _is(event, "MouseMove") and isinstance(event, QMouseEvent):
        return _move(event, view)
    if _is(event, "MouseButtonRelease") and isinstance(event, QMouseEvent):
        return _release(event, view)
    if _is(event, "Wheel") and isinstance(event, QWheelEvent):
        return _wheel(event)
    if _is(event, "KeyPress") and isinstance(event, QKeyEvent):
        return _key(event, pressed=True)
    if _is(event, "KeyRelease") and isinstance(event, QKeyEvent):
        return _key(event, pressed=False)
    if _is(event, "ShortcutOverride") and isinstance(event, QKeyEvent):
        return _probe(event)
    if _is(event, "Leave"):
        return Leave()
    if _is(event, "FocusIn"):
        return Focus(True, first_focus)
    if _is(event, "FocusOut"):
        return Focus(False, False)
    return None


def _frame_type() -> int:
    global _FRAME_REQUEST
    if _FRAME_REQUEST is None:
        _FRAME_REQUEST = enum_value(QEvent.registerEventType())
    return _FRAME_REQUEST


def _is(event: QEvent, name: str) -> bool:
    expected = getattr(getattr(QEvent, "Type", QEvent), name)
    return enum_value(event.type()) == enum_value(expected)


def _mods(flags: object) -> Mods:
    value = enum_value(flags)
    return Mods(
        shift=bool(value & _flag("KeyboardModifier", "ShiftModifier")),
        ctrl=bool(value & _flag("KeyboardModifier", "ControlModifier")),
        alt=bool(value & _flag("KeyboardModifier", "AltModifier")),
    )


def _flag(group: str, name: str) -> int:
    return enum_value(getattr(getattr(Qt, group, Qt), name))


_BUTTONS: Tuple[Tuple[str, Button], ...] = (
    ("LeftButton", "left"),
    ("MiddleButton", "middle"),
    ("RightButton", "right"),
)


def _button(button: object) -> Optional[Button]:
    value = enum_value(button)
    for name, label in _BUTTONS:
        if value & _flag("MouseButton", name):
            return label
    return None


def _held(buttons: object) -> FrozenSet[Button]:
    value = enum_value(buttons)
    return frozenset(label for name, label in _BUTTONS if value & _flag("MouseButton", name))


def _points(event: QEvent, view: QGraphicsView) -> Tuple[CanvasPoint, PortPoint]:
    pos = event_pos(event)
    scene = view.mapToScene(pos)
    return CanvasPoint(int(scene.x()), int(scene.y())), PortPoint(int(pos.x()), int(pos.y()))


def _press(event: QMouseEvent, view: QGraphicsView, double: bool) -> Optional[Press]:
    button = _button(event.button())
    if button is None:
        return None
    at, port = _points(event, view)
    return Press(at, port, button, _mods(event.modifiers()), double)


def _move(event: QMouseEvent, view: QGraphicsView) -> Move:
    at, port = _points(event, view)
    return Move(at, port, _held(event.buttons()), _mods(event.modifiers()))


def _release(event: QMouseEvent, view: QGraphicsView) -> Optional[Release]:
    button = _button(event.button())
    if button is None:
        return None
    at, port = _points(event, view)
    return Release(at, port, button, _mods(event.modifiers()))


def _wheel(event: QWheelEvent) -> Wheel:
    delta = event.angleDelta()
    pos = event_pos(event)
    return Wheel(PortPoint(int(pos.x()), int(pos.y())), int(delta.x()), int(delta.y()), _mods(event.modifiers()))


def _key(event: QKeyEvent, pressed: bool) -> Optional[Event]:
    name = _key_name(event)
    if name == "space" and event.isAutoRepeat():
        return None
    if pressed:
        return Key(name, _mods(event.modifiers()))
    return KeyUp(name)


def _probe(event: QKeyEvent) -> Optional[Probe]:
    name = _key_name(event)
    if name == "space" and event.isAutoRepeat():
        return None
    return Probe(name, _mods(event.modifiers()))


def _key_name(event: QKeyEvent) -> KeyName:
    key = enum_value(event.key())
    mods = _mods(event.modifiers())
    if mods.ctrl and key in (_key_code("Key_Plus"), _key_code("Key_Equal")):
        return "zoom_in"
    if mods.ctrl and key == _key_code("Key_Minus"):
        return "zoom_out"
    if mods.ctrl and key == _key_code("Key_0"):
        return "zoom_reset"
    if mods.ctrl and key == _key_code("Key_9"):
        return "zoom_fit"
    if key == _key_code("Key_Backtab") or (key == _key_code("Key_Tab") and mods.shift):
        return "backtab"
    named: Dict[int, KeyName] = {
        _key_code("Key_Escape"): "escape",
        _key_code("Key_Return"): "enter",
        _key_code("Key_Enter"): "enter",
        _key_code("Key_Tab"): "tab",
        _key_code("Key_Left"): "left",
        _key_code("Key_Right"): "right",
        _key_code("Key_Up"): "up",
        _key_code("Key_Down"): "down",
        _key_code("Key_Space"): "space",
        _key_code("Key_Shift"): "shift",
    }
    return named.get(key, "other")


def _key_code(name: str) -> int:
    return enum_value(getattr(getattr(Qt, "Key", Qt), name))

