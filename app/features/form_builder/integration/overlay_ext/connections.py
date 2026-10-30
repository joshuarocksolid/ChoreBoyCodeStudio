"""The Connections overlay (UX-ARR-006 .. 008).

F4, the toolbar button and Form > Overlays > Connections all toggle this kind.
The drag itself belongs to ``OverlayModes``. This module opens a picker when
the drag or the keyboard link finishes, and it is the only place that writes
a connection. Esc before a slot is chosen never reaches ``commit_step``.

The real event and step pickers belong to M6.1b (``qtside/pickers``). Until
that package exposes ``open_for_link``, a dialog in this file stands in.
"""

from __future__ import annotations

from typing import Any, Callable

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.events import steps_added
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.compat import is_signature, split_signature
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.logic.events_codec import EventStep, slot_step
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
            glyph="buddy",
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
    signal = QLineEdit("clicked()", dialog)
    signal.setObjectName("formBuilder.connectionPickerStub.signal")
    slot = QLineEdit("setFocus()" if receiver != sender else "clear()", dialog)
    slot.setObjectName("formBuilder.connectionPickerStub.slot")
    form.addRow("Signal", signal)
    form.addRow("Slot", slot)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
    form.addRow(buttons)

    def accept() -> None:
        if commit_step(surface, sender, signal.text().strip(), slot_step(receiver, slot.text().strip()), receiver):
            dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    exec_qt(dialog)


def _name(surface: Any, node: NodeId) -> str:
    found = surface.session.document.get(node)
    if isinstance(found, WidgetNode):
        return found.object_name
    return ""
