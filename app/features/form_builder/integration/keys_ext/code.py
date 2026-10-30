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
    method = _call(doc, sender, _default(doc, class_name)) or _call(doc, sender, "")
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
