"""Merge (FB404) and Open as text (FB401)."""

from __future__ import annotations

from app.features.form_builder.engine.commands.catalog_ext.events import MergeEventStorage
from app.features.form_builder.engine.logic.events_catalog import class_chain, event_words
from app.features.form_builder.engine.logic.storage import signal_of_property
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix
from app.features.form_builder.engine.logic.compat import node_class


def merge_event(context: FixContext) -> None:
    location = context.diagnostic.location
    sender = location.object_name or ""
    signal = signal_of_property(location.property or "") or ""
    if not sender or not signal:
        return
    doc = context.session.document
    node = doc.node(doc.by_name(sender)[0]) if doc.by_name(sender) else None
    chain = class_chain(QtClassTable.shared(), node_class(doc, QtClassTable.shared(), node)[0]) if node is not None else ()
    caption = "Merge the %s event" % event_words(signal, chain).header
    context.session.log.execute(MergeEventStorage(sender, signal, caption=caption))


def open_as_text(context: FixContext) -> None:
    surface = context.surface
    if surface is None:
        return
    source = surface.content_source()
    if source.mode == "visual":
        surface.toggle_source_view()
    editor = surface.source_editor()
    prop = context.diagnostic.location.property or ""
    if editor is None or not prop:
        return
    text = editor.toPlainText()
    at = text.find('name="%s"' % prop)
    if at < 0:
        return
    cursor = editor.textCursor()
    cursor.setPosition(at)
    editor.setTextCursor(cursor)
    editor.setFocus()


def register(registry: object) -> None:
    registry.add(ProblemFix("FB404", "merge-event", "Merge", merge_event))  # type: ignore[attr-defined]
    registry.add(ProblemFix("FB401", "open-as-text", "Open as text", open_as_text))  # type: ignore[attr-defined]
