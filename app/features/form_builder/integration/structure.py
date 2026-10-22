"""Read-only rows for the form structure tree.

Pure function of a document. No Qt.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, Node, SpacerNode, WidgetNode


def structure_rows(doc: UiDocument) -> Tuple[Tuple[int, str], ...]:
    """Pre-order labels for widgets, layouts, and spacers. Depth starts at 0."""
    rows: list[Tuple[int, str]] = []

    def walk(node: Node, depth: int) -> None:
        label = _label(node)
        child_depth = depth
        if label is not None:
            rows.append((depth, label))
            child_depth = depth + 1
        for _slot_name, kids in node.slots:
            for child in kids:
                walk(child, child_depth)

    walk(doc.ui, 0)
    return tuple(rows)


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


__all__ = ["structure_rows"]
