"""The Connections overlay (UX-ARR-006 .. 008).

F4, the toolbar button and Form > Overlays > Connections all toggle this kind.
The drag itself belongs to ``OverlayModes``. A finished link opens
``qtside/pickers.open_for_link`` at the drop point. A double-clicked arrow
opens ``open_for_step`` on that step. Esc before a choice writes nothing.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.events import steps_added
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.compat import is_signature, split_signature
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.logic.events_catalog import event_words, step_words
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.style.classes import widget_chain
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.overlay_ext import LinkGesture, LinkView, OverlayKind, ToggleSpec
from app.features.form_builder.qtside.canvas.layers.connections import LINK, LinkMark

KIND = "connections"
BANNER = (
    "Drag from a widget to the widget it should act on. "
    "Drop on the form's background to act on the form."
)
CHOOSE = "Choose the widget for %s to act on, then press Enter. Home picks the form."

Picker = Callable[..., None]


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
    """The canvas link opens M6.1b's picker."""
    from app.features.form_builder.qtside.pickers import open_for_link

    return open_for_link


def commit_step(surface: Any, sender: str, signal_signature: str, step: EventStep, receiver: str) -> bool:
    """One ``SetEventSteps`` entry. False when the step is already there or the command is refused.

    ``signal_signature`` is Designer text (``clicked()``). The catalog name passed
    to the engine is the bare name. Call this only after a slot is chosen.
    """
    if not is_signature(signal_signature):
        return False
    if step.verb == "slot" and not is_signature(step.slot):
        return False
    bare = split_signature(signal_signature)[0]
    document = surface.session.document
    current = read_event(document, sender, bare)
    for existing in current.steps:
        if existing.verb == step.verb and existing.target == step.target and existing.slot == step.slot and existing.method == step.method:
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
    """Open the event picker for a finished link. Esc writes nothing."""
    active_picker()(surface, source, target)


def _link(surface: Any, source: NodeId, target: NodeId) -> None:
    from app.features.form_builder.qtside.pickers import open_for_link

    open_for_link(surface, source, target, at=_drop_point(surface))


def _drop_point(surface: Any) -> object:
    """The global point of the drop, or None when the link had no pointer."""
    point = getattr(surface, "_connection_drop", None)
    if not isinstance(point, tuple) or len(point) < 2:
        return None
    canvas = getattr(getattr(surface, "workbench", None), "canvas", None)
    if canvas is None:
        return None
    from app.qt.QtCore import QPointF

    view = canvas.mapFromScene(QPointF(float(point[0]), float(point[1])))
    viewport = canvas.viewport()
    if viewport is None:
        return None
    return viewport.mapToGlobal(view)


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

