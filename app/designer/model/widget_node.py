"""Widget tree node model."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.designer.model.action_model import AddActionModel
from app.designer.model.property_value import PropertyValue


@dataclass
class WidgetNode:
    """Represents one `<widget>` node from a `.ui` file."""

    class_name: str
    object_name: str
    properties: dict[str, PropertyValue] = field(default_factory=dict)
    children: list["WidgetNode"] = field(default_factory=list)
    layout: "LayoutNode | None" = None
    add_actions: list[AddActionModel] = field(default_factory=list)
    unknown_children_xml: list[str] = field(default_factory=list)

    def find_by_object_name(self, object_name: str) -> "WidgetNode | None":
        """Return first descendant (or self) matching object name."""
        if self.object_name == object_name:
            return self
        for child in self.children:
            match = child.find_by_object_name(object_name)
            if match is not None:
                return match
        if self.layout is not None:
            for item in self.layout.items:
                if item.widget is None:
                    continue
                match = item.widget.find_by_object_name(object_name)
                if match is not None:
                    return match
        return None

    def collect_object_names(self) -> list[str]:
        """Collect object names from subtree in deterministic traversal order."""
        names = [self.object_name]
        for child in self.children:
            names.extend(child.collect_object_names())
        if self.layout is not None:
            for item in self.layout.items:
                if item.widget is not None:
                    names.extend(item.widget.collect_object_names())
        return names


from app.designer.model.layout_node import LayoutNode  # noqa: E402

