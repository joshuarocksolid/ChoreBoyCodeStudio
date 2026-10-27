from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropHost,
    DropIndicator,
    DropPayload,
    DropTarget,
    PayloadKind,
    blocked_ids,
    hosts_from,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import HitIndex, Rect
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.canvas.core.space import FormPoint
from app.features.form_builder.qtside.canvas.core.palette import fragment_for


def payload_for(doc: UiDocument, source_ids: Tuple[NodeId, ...], snap: bool = True) -> DropPayload:
    kind: PayloadKind = "widget"
    rowspan = 1
    colspan = 1
    if len(source_ids) == 1 and doc.contains(source_ids[0]):
        node = doc.node(source_ids[0])
        if isinstance(node, SpacerNode):
            kind = "spacer"
        elif isinstance(node, WidgetNode) and node.class_name == "QLabel":
            kind = "label"
        parent = doc.parent(source_ids[0])
        if isinstance(parent, LayoutItemNode):
            rowspan = 1 if parent.rowspan is None else parent.rowspan
            colspan = 1 if parent.colspan is None else parent.colspan
    return DropPayload(kind, source_ids, rowspan, colspan, snap)


# One tree per document epoch. A page switch bumps the epoch and rebuilds it.
_TREE: Dict[Tuple[int, int], DropHost] = {}


def resolve_at(
    doc: UiDocument,
    index: HitIndex,
    point: FormPoint,
    payload: DropPayload,
    rects: Optional[Dict[NodeId, Rect]] = None,
) -> DropTarget:
    if rects is not None:
        host = hosts_from(doc, rects)
    else:
        geometry = _rects(doc, index)
        host = _tree(doc, index, geometry)
    target = resolve_drop(
        host,
        (int(point.x), int(point.y)),
        payload,
        blocked_ids(doc, payload.source_ids),
    )
    if rects is not None:
        return target
    plus = index.plus_at(int(point.x), int(point.y))
    if plus is None:
        return target
    container, rect = plus
    node = doc.get(container)
    if not isinstance(node, WidgetNode) or node.class_name != "QTabWidget":
        return target
    return AcceptedDrop(
        "New tab",
        "New tab",
        container,
        "new_page",
        DropIndicator(rect, dashed=True),
        rect,
    )


def _tree(doc: UiDocument, index: HitIndex, geometry: Dict[NodeId, Rect]) -> DropHost:
    key = (id(doc), index.epoch)
    found = _TREE.get(key)
    if found is not None:
        return found
    host = hosts_from(doc, geometry)
    _TREE.clear()
    _TREE[key] = host
    return host


def drop_commands(
    doc: UiDocument,
    target: DropTarget,
    payload: DropPayload,
    insert_key: str,
    fragment: Optional[Fragment] = None,
) -> Tuple[Command, ...]:
    chosen = fragment
    if chosen is None and not payload.source_ids and insert_key:
        chosen = fragment_for(insert_key)
    return commands_for(doc, target, payload, chosen)


def _rects(doc: UiDocument, index: HitIndex) -> Dict[NodeId, Rect]:
    found: Dict[NodeId, Rect] = {}
    for node in doc.iter_preorder():
        rect = index.rect_of(node.id)
        if rect is not None:
            found[node.id] = rect
    return found
