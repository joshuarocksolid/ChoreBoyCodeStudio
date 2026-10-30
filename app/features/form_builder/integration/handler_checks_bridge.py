"""Run the window-file checks when the form changes or the window file is saved.

Not on each keystroke (UX D12). Inherited names come from the stock Qt class
(``dir``), never from importing the window file.
"""

from __future__ import annotations

import hashlib
import os
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
    # Same path, same text, and same form: the rows already published are the
    # rows a second check would produce. Skip the parse and the publish.
    key = _check_key(surface, session)
    memo = getattr(surface, "_cbcs_check_memo", None)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == key:
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
    surface._cbcs_followed = tuple(getattr(read, "followed", ()) or ())
    # The read may have followed a base the previous key did not know about.
    key = _check_key(surface, session)
    previous = memo[1] if isinstance(memo, tuple) and len(memo) == 2 else None
    surface._cbcs_check_memo = (key, rows)
    if previous == rows:
        return
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
        surface._cbcs_checks_unlisten = listen(lambda path: _on_saved(surface, path))
    publish(surface)


def _on_saved(surface: Any, path: object) -> None:
    """Rerun this form's checks only for its window file or a base of that file."""
    saved = str(path or "")
    if not saved:
        return
    scope = getattr(getattr(surface, "session", None), "scope", None)
    window = str(getattr(scope, "window_path", "") or "")
    root = str(getattr(scope, "project_root", "") or "")
    if window and _same_file(saved, window):
        publish(surface)
        return
    for relative in tuple(getattr(surface, "_cbcs_followed", ()) or ()):
        full = os.path.join(root, *str(relative).split("/")) if root else str(relative)
        if _same_file(saved, full):
            publish(surface)
            return


def _check_key(surface: Any, session: Any) -> Tuple[object, ...]:
    """Path, text digest, and the form state ``check_handlers`` reads.

    A new buffer, a saved base, or a new document revision misses. Nothing
    expires by time.
    """
    scope = getattr(session, "scope", None)
    path = str(getattr(scope, "window_path", "") or "")
    root = str(getattr(scope, "project_root", "") or "")
    bridge = getattr(surface, "code_bridge", None)
    reader = getattr(bridge, "text_of", None)
    text = reader(path) if callable(reader) and path else None
    if isinstance(text, str):
        digest: object = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    else:
        try:
            info = os.stat(path) if path else None
        except OSError:
            info = None
        digest = ("file", 0, -1) if info is None else ("file", info.st_mtime_ns, info.st_size)
    connect = str(session.document.ui.field("connectslotsbyname") or "") != "false"
    followed = tuple(getattr(surface, "_cbcs_followed", ()) or ())
    return (path, digest, int(session.document.revision), connect, _base_stamps(root, followed))


def _base_stamps(root: str, followed: Tuple[str, ...]) -> Tuple[object, ...]:
    found = []
    for relative in followed:
        full = os.path.join(root, *str(relative).split("/")) if root else str(relative)
        try:
            info = os.stat(full)
            found.append((str(relative), info.st_mtime_ns, info.st_size))
        except OSError:
            found.append((str(relative), 0, -1))
    return tuple(found)


def _same_file(left: str, right: str) -> bool:
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except OSError:
        return os.path.abspath(left) == os.path.abspath(right)


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
