"""Selected Qt binding and the small set of call-site differences."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from app.bootstrap.qt_binding_choice import ENV_VAR, select_binding

QT_API = select_binding()
IS_QT6 = QT_API == "PySide6"
QtCore = importlib.import_module(QT_API + ".QtCore")
QtGui = importlib.import_module(QT_API + ".QtGui")
QtWidgets = importlib.import_module(QT_API + ".QtWidgets")

# One object for the family. Qt 6 has it on QtGui. Qt 5 has it on QtWidgets.
_ACTION_FAMILY = (
    "QAction",
    "QActionGroup",
    "QShortcut",
    "QUndoCommand",
    "QUndoGroup",
    "QUndoStack",
)
for _name in _ACTION_FAMILY:
    if not hasattr(QtWidgets, _name) and hasattr(QtGui, _name):
        setattr(QtWidgets, _name, getattr(QtGui, _name))
    elif not hasattr(QtGui, _name) and hasattr(QtWidgets, _name):
        setattr(QtGui, _name, getattr(QtWidgets, _name))


def import_qt_module(short_name: str) -> ModuleType:
    """Import one Qt module. Qt 5 keeps QtSvgWidgets inside QtSvg."""
    if short_name == "QtSvgWidgets" and not IS_QT6:
        return importlib.import_module("PySide2.QtSvg")
    return importlib.import_module(QT_API + "." + short_name)


def exec_qt(obj: Any, *args: Any) -> Any:
    """Call exec on Qt 6 and exec_ on Qt 5. Never patch the class."""
    method = getattr(obj, "exec", None) if IS_QT6 else None
    return (method or obj.exec_)(*args)


def enum_value(value: Any) -> int:
    """Return an int for a Qt enum or flag on either binding."""
    raw = getattr(value, "value", value)
    return int(raw)


def event_pos(event: Any) -> Any:
    pos = getattr(event, "position", None)
    return pos().toPoint() if pos is not None else event.pos()


def event_global_pos(event: Any) -> Any:
    pos = getattr(event, "globalPosition", None)
    return pos().toPoint() if pos is not None else event.globalPos()


__all__ = [
    "ENV_VAR",
    "IS_QT6",
    "QT_API",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "enum_value",
    "event_global_pos",
    "event_pos",
    "exec_qt",
    "import_qt_module",
    "select_binding",
]
