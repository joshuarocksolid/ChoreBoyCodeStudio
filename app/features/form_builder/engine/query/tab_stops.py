"""Tab order and buddy queries (UX-OVL-004 .. 008, UX-MODE-002 .. 004). Qt-free.

A *stop* is a widget Tab can land on (``tree.takes_tab_focus``). A QDialogButtonBox
is not one (NoFocus, as in Designer): its buttons keep their own place. The *order* is the saved ``<tabstops>`` while the form has them and
the reading order otherwise. Everything here is O(form).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import effective_tab_order, reading_order
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue


@dataclass(frozen=True)
class Stop:
    name: str
    node: NodeId
    qt_class: str


def stops(doc: UiDocument, names: Optional[Tuple[str, ...]] = None) -> Tuple[Stop, ...]:
    """The stops of ``names`` (default: the effective order) that exist on the form."""
    order = effective_tab_order(doc) if names is None else names
    found: List[Stop] = []
    for name in order:
        ids = doc.by_name(name)
        node = doc.get(ids[0]) if ids else None
        if isinstance(node, WidgetNode):
            found.append(Stop(name, node.id, node.class_name))
    return tuple(found)


def follows_reading_order(doc: UiDocument) -> bool:
    """True while the form has no ``<tabstops>`` of its own."""
    return doc.tabstops() is None


def order_after_picks(order: Tuple[str, ...], picked: Tuple[str, ...]) -> Tuple[str, ...]:
    """``picked`` first, then every other stop of ``order`` in its old order."""
    chosen = set(picked)
    return tuple(picked) + tuple(name for name in order if name not in chosen)


def picks_through(order: Tuple[str, ...], name: str) -> Tuple[str, ...]:
    """The stops of ``order`` up to and including ``name``: where Shift+click continues from."""
    if name not in order:
        return ()
    return order[: order.index(name) + 1]


def caption(doc: UiDocument, node_id: NodeId) -> str:
    """A label's words without mnemonics or a trailing colon, else its object name."""
    node = doc.get(node_id)
    if not isinstance(node, WidgetNode):
        return ""
    entry = node.prop("text")
    text = entry.value.text if entry is not None and isinstance(entry.value, StringValue) else ""
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()
    text = text.rstrip(":").strip()
    return text or node.object_name


def caption_name(doc: UiDocument, node_id: NodeId) -> str:
    """A widget's object name, or an empty string for any other node."""
    node = doc.get(node_id)
    return node.object_name if isinstance(node, WidgetNode) else ""


def display_name(doc: UiDocument, object_name: str) -> str:
    """Buddy label, then the widget's own text, then the object name. ``&`` is removed."""
    if not object_name:
        return ""
    for label_id in labels(doc):
        if buddy_of(doc, label_id) != object_name:
            continue
        text = caption(doc, label_id)
        label = doc.get(label_id)
        if text and text != getattr(label, "object_name", ""):
            return text
    found = doc.by_name(object_name)
    node = doc.get(found[0]) if found else None
    if isinstance(node, WidgetNode):
        return caption(doc, node.id) or object_name
    return object_name


def buddy_of(doc: UiDocument, node_id: NodeId) -> Optional[str]:
    node = doc.get(node_id)
    if not isinstance(node, WidgetNode):
        return None
    entry = node.prop("buddy")
    if entry is not None and isinstance(entry.value, (CStringValue, StringValue)) and entry.value.text:
        return entry.value.text
    return None


def is_label(doc: UiDocument, node_id: NodeId) -> bool:
    node = doc.get(node_id)
    return isinstance(node, WidgetNode) and node.class_name == "QLabel"


def labels(doc: UiDocument) -> Tuple[NodeId, ...]:
    """Every QLabel with a name, in document order."""
    return tuple(
        node.id
        for node in doc.iter_preorder()
        if isinstance(node, WidgetNode) and node.class_name == "QLabel" and node.object_name
    )


def buddy_choices(doc: UiDocument) -> Tuple[Stop, ...]:
    """The fields a buddy can be: stops in reading order (UX-MODE-004)."""
    return stops(doc, reading_order(doc))


def form_row_pairs(doc: UiDocument) -> Tuple[Tuple[NodeId, str], ...]:
    """``(label id, field name)`` for each QFormLayout row of one label and one stop (UX-OVL-008)."""
    fields = {stop.name for stop in buddy_choices(doc)}
    pairs: List[Tuple[NodeId, str]] = []
    for node in doc.iter_preorder():
        if not isinstance(node, LayoutNode) or node.class_name != "QFormLayout":
            continue
        rows: Dict[int, Dict[str, WidgetNode]] = {}
        for item in node.items:
            content = item.content
            if not isinstance(content, WidgetNode) or (item.colspan or 1) > 1:
                continue
            role = "label" if (item.column or 0) == 0 else "field"
            rows.setdefault(item.row or 0, {})[role] = content
        for row in sorted(rows):
            label = rows[row].get("label")
            field = rows[row].get("field")
            if label is None or field is None or label.class_name != "QLabel":
                continue
            if label.object_name and field.object_name in fields:
                pairs.append((label.id, field.object_name))
    return tuple(pairs)
