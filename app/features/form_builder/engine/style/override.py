"""Does a style sheet already set this widget's colour? (UX-STYLE-010). Qt-free.

A colour row warns when the widget's own sheet or an ancestor's has a rule that
reaches the widget and sets what the row sets, because that sheet wins over a
palette colour.
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.style.selectors import match_sheet, shared_index
from app.features.form_builder.engine.style.sheet import parse_sheet
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue

TEXT_NAMES: FrozenSet[str] = frozenset({"color"})
BACKGROUND_NAMES: FrozenSet[str] = frozenset({"background", "background-color"})

def _sheet_of(node: object) -> str:
    entry = node.prop("styleSheet") if isinstance(node, WidgetNode) else None
    if entry is not None and isinstance(entry.value, StringValue):
        return entry.value.text
    return ""


def sheet_owners(document: UiDocument, widget: NodeId) -> Tuple[NodeId, ...]:
    """The widget and its ancestors that have a style sheet, nearest first."""
    found = []
    chain = (widget,) + document.ancestors(widget)
    for node_id in chain:
        node = document.get(node_id)
        if isinstance(node, WidgetNode) and _sheet_of(node).strip():
            found.append(node_id)
    return tuple(found)


def sheet_sets(document: UiDocument, widget: NodeId, names: FrozenSet[str]) -> bool:
    """True when a sheet on ``widget`` or above has a rule reaching ``widget`` that sets one of ``names``."""
    owners = sheet_owners(document, widget)
    if not owners:
        return False
    index = shared_index(document)
    for owner in owners:
        sheet = parse_sheet(_sheet_of(document.node(owner)))
        if sheet.errors():
            continue
        for match in match_sheet(index, owner, sheet):
            if widget not in match.ids:
                continue
            declarations = sheet.declarations if match.rule < 0 else sheet.rules[match.rule].declarations
            for declaration in declarations:
                if declaration.name.lower() in names:
                    return True
    return False
