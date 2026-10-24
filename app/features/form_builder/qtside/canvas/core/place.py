"""Qt-free drop resolution for one pointer move.

The gesture asks this. It does not paint and it does not import Qt.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import (
    DropPayload,
    DropTarget,
    PayloadKind,
    blocked_ids,
    hosts_from,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import HitIndex, Rect
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.canvas.core.space import FormPoint
from app.features.form_builder.qtside.canvas.core.palette import fragment_for


def payload_for(doc: UiDocument, source_ids: Tuple[NodeId, ...], snap: bool = True) -> DropPayload:
    kind: PayloadKind = "widget"
    if len(source_ids) == 1 and doc.contains(source_ids[0]):
        node = doc.node(source_ids[0])
        if isinstance(node, SpacerNode):
            kind = "spacer"
        elif isinstance(node, WidgetNode) and node.class_name == "QLabel":
            kind = "label"
    return DropPayload(kind, source_ids, snap=snap)


def resolve_at(
    doc: UiDocument,
    index: HitIndex,
    point: FormPoint,
    payload: DropPayload,
    rects: Optional[Dict[NodeId, Rect]] = None,
) -> DropTarget:
    """One target at a form-pixel point. ``rects`` overrides the hit index."""
    geometry = rects if rects is not None else _rects(doc, index)
    host = hosts_from(doc, geometry)
    return resolve_drop(
        host,
        (int(point.x), int(point.y)),
        payload,
        blocked_ids(doc, payload.source_ids),
    )


def drop_commands(
    doc: UiDocument,
    target: DropTarget,
    payload: DropPayload,
    insert_key: str,
) -> Tuple[Command, ...]:
    fragment: Optional[Fragment] = None
    if not payload.source_ids and insert_key:
        fragment = fragment_for(insert_key)
    return commands_for(doc, target, payload, fragment)


def _rects(doc: UiDocument, index: HitIndex) -> Dict[NodeId, Rect]:
    found: Dict[NodeId, Rect] = {}
    for node in doc.iter_preorder():
        rect = index.rect_of(node.id)
        if rect is not None:
            found[node.id] = rect
    return found
