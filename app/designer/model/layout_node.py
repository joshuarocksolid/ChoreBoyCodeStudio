"""Layout tree node model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpacerItem:
    """Represents a `<spacer>` layout item."""

    name: str


@dataclass
class LayoutItem:
    """Represents one `<item>` in a Qt layout."""

    widget: "WidgetNode | None" = None
    layout: "LayoutNode | None" = None
    spacer: SpacerItem | None = None
    unknown_xml: list[str] = field(default_factory=list)


@dataclass
class LayoutNode:
    """Represents one `<layout>` node from a `.ui` file."""

    class_name: str
    object_name: str
    items: list[LayoutItem] = field(default_factory=list)
    unknown_children_xml: list[str] = field(default_factory=list)


from app.designer.model.widget_node import WidgetNode  # noqa: E402

