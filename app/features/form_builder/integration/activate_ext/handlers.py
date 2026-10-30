"""Double-click writes code for a widget's default event (UX D8, UX-CODE-018).

``claims`` only looks at the form. It does not read the window file.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.codec import marker_read_only
from app.features.form_builder.engine.logic.compat import node_class
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.logic.events_catalog import class_chain, default_event, event_words
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ActionNode
from app.features.form_builder.integration.activate_ext import Activator
from app.features.form_builder.integration.handlers import service
from app.features.form_builder.integration.handlers_code import NO_FORMS, NO_PROJECT
from app.features.form_builder.qtside.pickers import open_event_picker, open_method_page

_D8 = frozenset({
    "QPushButton",
    "QToolButton",
    "QCommandLinkButton",
    "QCheckBox",
    "QRadioButton",
    "QDialogButtonBox",
})
_WRITE = "double-click to write code"
_GO = "double-click to go to its code"
_NEWER = "This form's behavior was saved by a newer version of Code Studio, so it can't be changed here."


def claims(doc: UiDocument, node_id: NodeId) -> Optional[str]:
    sender, class_name = _target(doc, node_id)
    if not sender or not _claimed_class(doc, node_id, class_name):
        return None
    signal = _default(doc, class_name)
    if not signal:
        return None
    state = read_event(doc, sender, signal)
    for step in state.steps:
        if step.verb == "call" and step.method:
            return _GO
    return _WRITE


def activate(surface: Any, node_id: NodeId) -> None:
    write_for(surface, node_id)


def write_for(surface: Any, node_id: NodeId) -> None:
    doc = surface.session.document
    sender, class_name = _target(doc, node_id)
    if not sender:
        return
    signal = _default(doc, class_name)
    if not signal:
        return
    scope = surface.session.scope
    if not getattr(scope, "generates", False):
        open_event_picker(surface, sender, "")
        _narrate(surface, NO_PROJECT if not getattr(scope, "project_root", None) else NO_FORMS)
        return
    state = read_event(doc, sender, signal)
    for step in state.steps:
        if step.verb == "call" and step.method:
            if not service().go_to(surface, step.method):
                file_name = _file_name(scope)
                _narrate(surface, "%s() isn't in %s yet. Press Ctrl+. to create it." % (step.method, file_name))
            return
    if marker_read_only(doc.root.prop("cbcsLogic")):
        _narrate(surface, _NEWER)
        return
    open_method_page(surface, sender, signal)


def menu_title(doc: UiDocument, node_id: NodeId) -> str:
    sender, class_name = _target(doc, node_id)
    signal = _default(doc, class_name) if sender else ""
    if not signal:
        return ""
    header = event_words(signal, class_chain(QtClassTable.shared(), class_name)).header
    return "Write code for \u201c%s\u201d" % header


def register(registry: Any) -> None:
    registry.add(Activator("handlers", claims, activate))


def _claimed_class(doc: UiDocument, node_id: NodeId, class_name: str) -> bool:
    node = doc.get(node_id)
    if isinstance(node, ActionNode):
        return True
    return class_name in _D8


def _default(doc: UiDocument, class_name: str) -> str:
    if not class_name:
        return ""
    return default_event(QtClassTable.shared(), class_name) or ""


def _target(doc: UiDocument, node_id: NodeId) -> Tuple[str, str]:
    node = doc.get(node_id)
    if node is None:
        return "", ""
    sender = ""
    for field in ("object_name", "name"):
        value = node.field(field) if hasattr(node, "field") else None
        if isinstance(value, str) and value:
            sender = value
            break
    if isinstance(node, ActionNode):
        return sender, "QAction"
    class_name, _slots = node_class(doc, QtClassTable.shared(), node)
    return sender, class_name


def _file_name(scope: Any) -> str:
    import os

    path = str(getattr(scope, "window_path", "") or "")
    return os.path.basename(path) if path else "the window file"


def _narrate(surface: Any, sentence: str) -> None:
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)
