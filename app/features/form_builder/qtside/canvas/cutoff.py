"""Which realized widgets clip their text.

A full walk happens when the preview changes. An edit passes the sibling
ids the caller already has. This module does not walk a form from the
inspector.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from app.qt.QtWidgets import QWidget

from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import cuts_off, facts_from_document, project
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.qtside.realize.api import Realizer


def cutoff_ids(document: UiDocument, realizer: Realizer) -> Tuple[NodeId, ...]:
    """Every realized widget whose hint exceeds a side it cannot grow."""
    found = []
    for node in document.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        if _clipped(document, realizer, node.id):
            found.append(node.id)
    return tuple(found)


def cutoff_among(
    document: UiDocument, realizer: Realizer, ids: Sequence[NodeId]
) -> Tuple[NodeId, ...]:
    """The members of ``ids`` that are cut off. Does not look at anyone else."""
    return tuple(node_id for node_id in ids if _clipped(document, realizer, node_id))


def merge_cutoff(
    previous: Sequence[NodeId], scanned: Sequence[NodeId], still: Sequence[NodeId]
) -> Tuple[NodeId, ...]:
    """Replace the scanned ids in ``previous`` with the ones that still clip."""
    drop = set(scanned)
    kept = [node_id for node_id in previous if node_id not in drop]
    kept.extend(still)
    return tuple(dict.fromkeys(kept))


def edited_siblings(document: UiDocument, changeset: object) -> Optional[Tuple[NodeId, ...]]:
    """Sibling widgets of an edit, when the parent already lists them.

    None means the caller must not walk the form to go find them.
    """
    if not isinstance(changeset, ChangeSet):
        return None
    owners = [node_id for node_id, _kind, _name in changeset.property_dirty]
    owners.extend(changeset.structure_dirty)
    if not owners:
        return None
    found = []
    for node_id in owners:
        group = _sibling_group(document, node_id)
        if group is None:
            continue
        found.extend(group)
    if not found:
        return None
    return tuple(dict.fromkeys(found))


def _clipped(document: UiDocument, realizer: Realizer, node_id: NodeId) -> bool:
    node = document.get(node_id)
    widget = realizer.widget_for(node_id)
    if not isinstance(node, WidgetNode) or not isinstance(widget, QWidget):
        return False
    if widget.width() <= 0 or widget.height() <= 0:
        return False
    policy = widget.sizePolicy()
    facts = facts_from_document(
        document,
        node,
        _policy_name(policy.horizontalPolicy()),
        _policy_name(policy.verticalPolicy()),
        "",
    )
    panel = project((facts,))
    hint = widget.sizeHint()
    return cuts_off(
        int(widget.width()),
        int(widget.height()),
        int(hint.width()),
        int(hint.height()),
        panel.horizontal.mode,
        panel.vertical.mode,
    )


def _sibling_group(document: UiDocument, node_id: NodeId) -> Optional[Tuple[NodeId, ...]]:
    node = document.get(node_id)
    if isinstance(node, LayoutItemNode) and node.parent_id is not None:
        node = document.get(node.parent_id)
    if isinstance(node, LayoutNode):
        return _layout_widgets(node)
    if not isinstance(node, WidgetNode):
        return None
    parent = document.get(node.parent_id) if node.parent_id is not None else None
    if isinstance(parent, LayoutItemNode) and parent.parent_id is not None:
        layout = document.get(parent.parent_id)
        if isinstance(layout, LayoutNode):
            return _layout_widgets(layout)
    if isinstance(parent, WidgetNode):
        return tuple(child.id for child in parent.child_widgets)
    return (node.id,)


def _layout_widgets(layout: LayoutNode) -> Optional[Tuple[NodeId, ...]]:
    found = []
    for item in layout.items:
        content = item.content
        if isinstance(content, WidgetNode):
            found.append(content.id)
    if not found:
        return None
    return tuple(found)


def _policy_name(value: object) -> str:
    name = getattr(value, "name", None)
    text = name if isinstance(name, str) and name else str(value)
    if "::" in text:
        text = text.rsplit("::", 1)[-1]
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text or "Preferred"
