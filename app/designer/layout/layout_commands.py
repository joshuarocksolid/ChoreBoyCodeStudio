"""Model-level layout command helpers for designer forms."""

from __future__ import annotations

from app.designer.model import LayoutItem, LayoutNode, WidgetNode

_SUPPORTED_LAYOUT_CLASSES = {"QVBoxLayout", "QHBoxLayout", "QGridLayout"}


def apply_layout_to_widget(widget: WidgetNode, layout_class_name: str, *, layout_object_name: str) -> None:
    """Apply a layout to widget and move direct children into layout items."""
    if layout_class_name not in _SUPPORTED_LAYOUT_CLASSES:
        raise ValueError(f"Unsupported layout class: {layout_class_name}")
    if widget.layout is not None:
        raise ValueError(f"Widget already has layout: {widget.object_name}")

    items = [LayoutItem(widget=child) for child in widget.children]
    widget.children = []
    widget.layout = LayoutNode(
        class_name=layout_class_name,
        object_name=layout_object_name,
        items=items,
    )


def break_layout(widget: WidgetNode) -> None:
    """Remove layout from widget and move contained widgets back to children."""
    if widget.layout is None:
        return
    restored_children: list[WidgetNode] = []
    for item in widget.layout.items:
        if item.widget is not None:
            restored_children.append(item.widget)
    widget.children.extend(restored_children)
    widget.layout = None
