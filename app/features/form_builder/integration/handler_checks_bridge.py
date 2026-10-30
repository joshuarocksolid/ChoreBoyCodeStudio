"""Run the window-file checks when the form changes or the window file is saved.

Not on each keystroke (UX D12). Inherited names come from the stock Qt class
(``dir``), never from importing the window file.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS
from app.features.form_builder.engine.project.handler_checks import check_handlers
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.integration.handlers_code import SERVICE

SOURCE = "handlers"
_NAMES: Dict[str, Tuple[str, ...]] = {}


def inherited_names(class_name: str) -> Tuple[str, ...]:
    """Public names of a stock Qt class, including what it inherits."""
    if class_name in _NAMES:
        return _NAMES[class_name]
    found = _qt_type(class_name)
    names = tuple(name for name in dir(found) if not name.startswith("_")) if found is not None else ()
    _NAMES[class_name] = names
    return names


def publish(surface: Any) -> None:
    from app.features.form_builder.engine import diagnostic_codes

    diagnostic_codes.discover()
    session = getattr(surface, "session", None)
    if session is None or getattr(session, "disposed", False):
        return
    read = SERVICE.reading(surface)
    classes = QtClassTable.shared()
    base = _qt_base(session, read)
    connect = str(session.document.ui.field("connectslotsbyname") or "") != "false"
    rows = check_handlers(
        session.document,
        read,
        classes=classes,
        registry=_registry(session),
        inherited=inherited_names(base),
        connect_by_name=connect,
    )
    session.diagnostics.publish(SOURCE, rows)


def arm(surface: Any) -> None:
    """Publish now, after a form edit, and when the window file's tab is saved."""
    if getattr(surface, "_cbcs_handler_checks", False):
        return
    surface._cbcs_handler_checks = True

    def refresh(_change: object = None) -> None:
        publish(surface)

    surface.session.log.subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)
    bridge = getattr(surface, "code_bridge", None)
    listen = getattr(bridge, "on_saved", None)
    if callable(listen):
        surface._cbcs_checks_unlisten = listen(lambda _path: publish(surface))
    publish(surface)


def _registry(session: Any) -> Tuple[object, ...]:
    from app.features.form_builder.integration.custom_registry import registry_of

    found = registry_of(session)
    entries = getattr(found, "entries", None)
    if not callable(entries):
        return ()
    return tuple(entries())


def _qt_base(session: Any, read: Any) -> str:
    bases = getattr(getattr(read, "facts", None), "bases", ()) or ()
    classes = QtClassTable.shared()
    for name in bases:
        if classes.class_info(str(name)) is not None:
            return str(name)
    root = getattr(session.document, "root", None)
    class_name = getattr(root, "class_name", "") or "QWidget"
    return str(class_name)


def _qt_type(class_name: str) -> Optional[type]:
    from app.qt import QtCore, QtGui, QtWidgets

    for module in (QtWidgets, QtGui, QtCore):
        found = getattr(module, class_name, None)
        if isinstance(found, type):
            return found
    return None
