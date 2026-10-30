"""The Connections overlay (UX-ARR-006 .. 008).

F4, the toolbar button and Form > Overlays > Connections all toggle this kind.
The drag itself belongs to ``OverlayModes``. This module opens a picker when
the drag or the keyboard link finishes, and it is the only place that writes
a connection. Esc before a slot is chosen never reaches ``commit_step``.

The real event and step pickers belong to M6.1b (``qtside/pickers``). Until
that package exposes ``open_for_link``, a dialog in this file stands in.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.events import steps_added
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.compat import is_signature, signature_text, split_signature
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.logic.events_catalog import event_words, step_words
from app.features.form_builder.engine.logic.events_codec import EventStep, slot_step
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.style.classes import widget_chain
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.overlay_ext import LinkGesture, LinkView, OverlayKind, ToggleSpec
from app.features.form_builder.qtside.canvas.layers.connections import LINK, LinkMark
from app.qt.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit
from app.qt.qt_compat import exec_qt

KIND = "connections"
BANNER = (
    "Drag from a widget to the widget it should act on. "
    "Drop on the form's background to act on the form."
)
CHOOSE = "Choose the widget for %s to act on, then press Enter. Home picks the form."
STUB_NAME = "formBuilder.connectionPickerStub"

Picker = Callable[[Any, NodeId, NodeId], None]


def register(registry: Any) -> None:
    registry.add(
        OverlayKind(
            kind=KIND,
            title="Connections",
            banner_text=BANNER,
            glyph="connections",
            layer=LINK,
            state=_mark,
            toggle=ToggleSpec("Connections", "Connections (F4)"),
            link=LinkGesture(
                link=_link,
                start_status=lambda name: CHOOSE % name,
                hover_status=lambda name: "%s · drag to another widget to connect" % name,
            ),
        )
    )


def active_picker() -> Picker:
    """M6.1b's ``open_for_link`` when that package is installed, otherwise the stub."""
    try:
        from app.features.form_builder.qtside import pickers
    except ImportError:
        return _stub_open
    found = getattr(pickers, "open_for_link", None)
    if found is None:
        return _stub_open
    return found


def commit_step(surface: Any, sender: str, signal_signature: str, step: EventStep, receiver: str) -> bool:
    """One ``SetEventSteps`` entry. False when the step is already there or the command is refused.

    ``signal_signature`` is Designer text (``clicked()``). The catalog name passed
    to the engine is the bare name. Call this only after a slot is chosen.
    """
    if not is_signature(signal_signature):
        surface.narrate("Enter a signal the way Designer writes it, such as clicked().")
        return False
    if step.verb == "slot" and not is_signature(step.slot):
        surface.narrate("Enter a slot the way Designer writes it, such as setFocus().")
        return False
    bare = split_signature(signal_signature)[0]
    document = surface.session.document
    current = read_event(document, sender, bare)
    for existing in current.steps:
        if existing.verb == step.verb and existing.target == step.target and existing.slot == step.slot and existing.method == step.method:
            surface.narrate("That connection is already there.")
            return False
    caption = "Connect %s to %s" % (sender, receiver)
    try:
        surface.session.log.execute(steps_added(document, sender, bare, (step,), caption=caption))
    except CommandRejected as refused:
        surface.narrate(str(refused))
        return False
    return True


def _mark(view: LinkView) -> LinkMark:
    return LinkMark(view.source, view.candidate, view.pointer, view.dragging)


def choose_step(surface: Any, source: NodeId, target: NodeId) -> None:
    """Open the picker for a finished link or a double-clicked arrow. Esc writes nothing."""
    active_picker()(surface, source, target)


def _link(surface: Any, source: NodeId, target: NodeId) -> None:
    choose_step(surface, source, target)


def _stub_open(surface: Any, source: NodeId, target: NodeId) -> None:
    sender = _name(surface, source)
    receiver = _name(surface, target)
    if not sender or not receiver:
        return
    dialog = QDialog(surface)
    dialog.setObjectName(STUB_NAME)
    dialog.setWindowTitle("Connect %s to %s" % (sender, receiver))
    form = QFormLayout(dialog)
    sender_node = surface.session.document.get(source)
    signal = QLineEdit(_default_signal(sender_node), dialog)
    signal.setObjectName("formBuilder.connectionPickerStub.signal")
    slot = QLineEdit("setFocus()" if receiver != sender else "clear()", dialog)
    slot.setObjectName("formBuilder.connectionPickerStub.slot")
    form.addRow("Signal", signal)
    form.addRow("Slot", slot)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setDefault(True)
        ok.setAutoDefault(True)
    form.addRow(buttons)

    def accept() -> None:
        if commit_step(surface, sender, signal.text().strip(), slot_step(receiver, slot.text().strip()), receiver):
            dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    exec_qt(dialog)


def window_file(surface: Any) -> str:
    """``<stem>_window.py`` for the open form, or empty when it has no path."""
    path = str(getattr(surface, "_path", "") or "")
    stem = os.path.splitext(os.path.basename(path))[0]
    if not stem:
        return ""
    return "%s_window.py" % stem


def step_sentence(doc: Any, step: EventStep) -> str:
    """One step in the words of UX 13.3.8. ``{w}`` is the display name and the object name."""
    target = step.target if step.verb == "slot" else (doc.root.object_name if step.verb == "call" else "")
    named = "%s (%s)" % (display_name(doc, target), target) if target else ""
    chain: Tuple[str, ...] = ()
    found = doc.by_name(target) if target else None
    node = doc.get(found[0]) if found else None
    if isinstance(node, WidgetNode):
        chain = widget_chain(doc, node)
    return step_words(step, named, is_form=(bool(target) and target == doc.root.object_name), target_chain=chain)


def arrow_status(doc: Any, sender: str, signal: str, index: int) -> str:
    """UX-ARR-010. Empty when the step is no longer in the document."""
    bare = split_signature(signal)[0]
    state = read_event(doc, sender, bare)
    if index < 0 or index >= len(state.steps):
        return ""
    found = doc.by_name(sender)
    node = doc.get(found[0]) if found else None
    chain = widget_chain(doc, node) if isinstance(node, WidgetNode) else ()
    return "When %s is %s: %s. Click to select, Delete to remove." % (
        display_name(doc, sender),
        event_words(bare, chain).header,
        step_sentence(doc, state.steps[index]),
    )


def code_status(method: str, file_name: str) -> str:
    """The ``{ }`` chip sentence. A form with no path uses the no-window-file line."""
    if not file_name:
        return "This form isn't in a project, so it has no window file."
    return "Calls %s() in %s. Click to go to the code." % (method, file_name)


def _default_signal(node: object) -> str:
    """The class's default event, so OK writes a step the engine accepts.

    A line edit stores ``returnPressed()``. ``editingFinished`` fires when focus
    leaves the field, which would start another link on every Tab.
    """
    if not isinstance(node, WidgetNode):
        return "clicked()"
    from app.features.form_builder.engine.logic.events_catalog import default_event
    from app.features.form_builder.engine.style.classes import stock_chain
    from app.features.form_builder.engine.ui4.defaults import QtClassTable

    if "QLineEdit" in stock_chain(node.class_name):
        return signature_text("returnPressed", ())
    name = default_event(QtClassTable.shared(), node.class_name) or "clicked"
    return signature_text(name, ())


def _name(surface: Any, node: NodeId) -> str:
    found = surface.session.document.get(node)
    if isinstance(found, WidgetNode):
        return found.object_name
    return ""
