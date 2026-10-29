"""A rename keeps ``#name`` selectors in style sheets pointing at the widget (UX-STYLE-010).

The Text colour row writes ``#okButton { color: ... }`` into a sheet that has
rules. When ``okButton`` is renamed, every ``#okButton`` in a selector of any
style sheet in the form becomes ``#newName`` in the same undo step. A hex
colour in a value (``#fff``) is never touched.
"""

from __future__ import annotations

from typing import FrozenSet, List, Optional, Tuple

from app.features.form_builder.engine.commands.ops import Op, SetPropertyOp
from app.features.form_builder.engine.commands.participants import ParticipantRegistry
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.style.edit import mentions_selector, rename_selectors
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue

PROPERTY = "styleSheet"


class StyleRenameParticipant:
    participant_id = "style"

    def rename_ops(
        self,
        doc: UiDocument,
        renames: Tuple[Tuple[str, str], ...],
        scope: Optional[FrozenSet[NodeId]],
    ) -> Tuple[Op, ...]:
        mapping = {old: new for old, new in renames if old != new}
        if not mapping:
            return ()
        found: List[Op] = []
        for node in doc.iter_widgets():
            if scope is not None and node.id not in scope:
                continue
            entry = _sheet(node)
            if entry is None or not isinstance(entry.value, StringValue):
                continue
            text = rename_selectors(entry.value.text, mapping)
            if text == entry.value.text:
                continue
            replacement = PropertyEntry(
                "property",
                PROPERTY,
                _with_text(entry.value, text),
                entry.stdset,
                entry.extra_attrs,
            )
            found.append(SetPropertyOp(node.id, "property", PROPERTY, replacement, None))
        return tuple(found)

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        found: List[Tuple[NodeId, str]] = []
        for node in doc.iter_widgets():
            entry = _sheet(node)
            if entry is not None and isinstance(entry.value, StringValue) and mentions_selector(entry.value.text, name):
                found.append((node.id, PROPERTY))
        return tuple(found)


def _sheet(node: WidgetNode) -> Optional[PropertyEntry]:
    return node.prop(PROPERTY)


def _with_text(value: StringValue, text: str) -> StringValue:
    return StringValue(text, value.notr, value.comment, value.extracomment, value.id)


def register(registry: ParticipantRegistry) -> None:
    registry.add_rename(StyleRenameParticipant())
