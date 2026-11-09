"""F12 goes to the method the selection names (UX-CODE-009).

The shell uses F12 for Go to Definition in the editor. ``shell_action_id``
marks this row as that same shortcut so the two contexts do not both claim it.
"""

from __future__ import annotations

import os
from typing import Any

from app.qt.QtWidgets import QApplication

from app.features.form_builder.engine.logic.events import read_event, read_events
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.integration.activate_ext.handlers import _default, _target
from app.features.form_builder.integration.handlers import service

_FORM = ("form_tab",)
_NO_CODE = "%s has no code yet. Double-click it, or press Ctrl+Shift+E to add an event."
_MISSING = "%s() isn't in %s yet. Press Ctrl+. to create it."


def go_to_code(surface: Any) -> None:
    focused = _focused_method()
    if focused:
        _open(surface, focused)
        return
    session = surface.session
    doc = session.document
    ids = session.selection.state.ids
    if len(ids) != 1 or ids[0] == doc.root.id:
        service().go_to(surface, "")
        return
    sender, class_name = _target(doc, ids[0])
    if not sender or sender == doc.root.object_name:
        service().go_to(surface, "")
        return
    signal = _default(doc, class_name)
    method = _call(doc, sender, signal) or _call(doc, sender, "") or _named(surface, sender, signal)
    if not method:
        _narrate(surface, _NO_CODE % display_name(doc, sender))
        return
    _open(surface, method)


def register(keys: Any) -> None:
    keys.key(
        "form.action.goToCode",
        "Go to code",
        "F12",
        _FORM,
        shell_action_id="shell.action.edit.goToDefinition",
        run=go_to_code,
    )


def _open(surface: Any, method: str) -> None:
    if service().go_to(surface, method):
        return
    _narrate(surface, _MISSING % (method, _file(surface)))


def _focused_method() -> str:
    widget = QApplication.focusWidget()
    while widget is not None:
        method = getattr(widget, "method_name", "") or ""
        if method and getattr(widget, "objectName", lambda: "")() != "formBuilder.events.place":
            return str(method)
        widget = widget.parentWidget()
    return ""


def _method_name(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("async def "):
        stripped = stripped[len("async "):]
    if not stripped.startswith("def "):
        return ""
    found = stripped[4:].split("(", 1)[0].strip()
    return found if found.isidentifier() else ""


def _def_on_line(source: str, cursor: int) -> str:
    """The method a ``def`` line names, including when the caret is at column 1."""
    line_no = source[: max(0, cursor)].count("\n")
    lines = source.splitlines()
    if line_no >= len(lines):
        return ""
    for offset in (0, 1):
        index = line_no + offset
        if index >= len(lines):
            break
        text = lines[index].strip()
        if text.startswith("@"):
            continue
        found = _method_name(text)
        if found:
            return found
        if offset == 0 and text:
            return ""
    return ""


def _enclosing_def(source: str, cursor: int) -> str:
    """The method whose body contains the caret, when the caret is not on a word."""
    line_no = source[: max(0, cursor)].count("\n")
    lines = source.splitlines()
    for index in range(min(line_no, len(lines) - 1), -1, -1):
        found = _method_name(lines[index])
        if found:
            return found
        if lines[index].strip().startswith("class "):
            return ""
    return ""


def return_to_form(window: Any, file_path: str, source: str, symbol: str, cursor: int) -> bool:
    """F12 on a ``def`` the form names opens the form and selects that widget."""
    path = str(file_path or "")
    name = os.path.basename(path)
    named = _def_on_line(source, cursor) or _enclosing_def(source, cursor)
    if named:
        symbol = named
    if not name.endswith("_window.py") or not symbol:
        return False
    line_no = source[: max(0, cursor)].count("\n")
    lines = source.splitlines()
    if ("def %s" % symbol) not in "\n".join(lines[: line_no + 2]):
        return False
    ui = os.path.join(os.path.dirname(path), name[: -len("_window.py")] + ".ui")
    if not os.path.isfile(ui):
        return False
    opener = getattr(window, "_editor_tab_workflow", None)
    open_at = getattr(opener, "open_file_at_line", None)
    registry = getattr(window, "_tab_content_registry", None)
    finder = getattr(registry, "surface_for_path", None)
    surface = finder(ui) if callable(finder) else None
    if surface is None and callable(finder):
        surface = finder(os.path.abspath(ui))
    live = getattr(getattr(surface, "session", None), "document", None) if surface is not None else None
    sender = _sender_from_document(live, symbol) if live is not None else ""
    if not sender:
        sender = _sender_named(ui, symbol)
    if not sender or not callable(open_at):
        return False
    open_at(ui, 1)
    if surface is None and callable(finder):
        surface = finder(ui) or finder(os.path.abspath(ui))
    if surface is None:
        return True
    document = surface.session.document
    found = document.by_name(sender)
    if found:
        from app.features.form_builder.engine.query.selection import SelectionSource

        surface.session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    return True


def _sender_named(ui_path: str, symbol: str) -> str:
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import read_ui

    try:
        text = open(ui_path, encoding="utf-8").read()
        document = read_ui(text, allocator=IdAllocator()).document
    except (OSError, ValueError):
        return ""
    return _sender_from_document(document, symbol)


def _sender_from_document(document: Any, symbol: str) -> str:
    from app.features.form_builder.engine.logic.events import read_events

    if document is None or not symbol:
        return ""
    if symbol.startswith("on_"):
        rest = symbol[3:]
        for name in sorted(document.names(), key=len, reverse=True):
            prefix = name + "_"
            if rest.startswith(prefix) and rest[len(prefix):]:
                return name
    for state in read_events(document):
        for step in state.steps:
            if step.verb == "call" and step.method == symbol:
                return state.sender
    return ""


def _named(surface: Any, sender: str, signal: str) -> str:
    from app.features.form_builder.integration.activate_ext.handlers import named_method

    return named_method(surface, sender, signal)


def _call(doc: Any, sender: str, signal: str) -> str:
    states = (read_event(doc, sender, signal),) if signal else read_events(doc)
    for state in states:
        if state.sender != sender:
            continue
        for step in state.steps:
            if step.verb == "call" and step.method:
                return str(step.method)
    return ""


def _file(surface: Any) -> str:
    scope = getattr(surface.session, "scope", None)
    path = str(getattr(scope, "window_path", "") or "")
    return os.path.basename(path) if path else "the window file"


def _narrate(surface: Any, sentence: str) -> None:
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)
