"""Read-only rows for the form structure tree.

Pure function of a document. No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, Node, SpacerNode, WidgetNode


@dataclass(frozen=True)
class StructureEntry:
    """One outline row. ``node_id`` is what the selection model stores."""

    depth: int
    label: str
    node_id: NodeId


def structure_entries(doc: UiDocument) -> Tuple[StructureEntry, ...]:
    """Pre-order outline rows. Depth starts at 0."""
    rows: list[StructureEntry] = []

    def walk(node: Node, depth: int) -> None:
        label = _label(node)
        child_depth = depth
        if label is not None:
            rows.append(StructureEntry(depth, label, node.id))
            child_depth = depth + 1
        for _slot_name, kids in node.slots:
            for child in kids:
                walk(child, child_depth)

    walk(doc.ui, 0)
    return tuple(rows)


def structure_rows(doc: UiDocument) -> Tuple[Tuple[int, str], ...]:
    """Pre-order labels for widgets, layouts, and spacers. Depth starts at 0."""
    return tuple((entry.depth, entry.label) for entry in structure_entries(doc))


def _label(node: Node) -> Optional[str]:
    if isinstance(node, WidgetNode):
        if node.object_name:
            return f"{node.class_name}  {node.object_name}"
        return node.class_name
    if isinstance(node, LayoutNode):
        if node.object_name:
            return f"{node.class_name}  {node.object_name}"
        return node.class_name
    if isinstance(node, SpacerNode):
        if node.name:
            return f"Spacer  {node.name}"
        return "Spacer"
    return None


__all__ = ["StructureEntry", "structure_entries", "structure_rows"]
