"""Top-level in-memory UI model."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.designer.model.action_model import (
    AddActionModel,
    ActionGroupModel,
    ActionModel,
    ButtonGroupModel,
    ZOrderModel,
)
from app.designer.model.connection_model import ConnectionModel
from app.designer.model.custom_widget_model import CustomWidgetModel
from app.designer.model.resource_model import ResourceModel
from app.designer.model.widget_node import WidgetNode


@dataclass
class UIModel:
    """Canonical model for Designer edit operations."""

    form_class_name: str
    root_widget: WidgetNode
    ui_version: str = "4.0"
    connections: list[ConnectionModel] = field(default_factory=list)
    resources: list[ResourceModel] = field(default_factory=list)
    tab_stops: list[str] = field(default_factory=list)
    custom_widgets: list[CustomWidgetModel] = field(default_factory=list)
    actions: list[ActionModel] = field(default_factory=list)
    action_groups: list[ActionGroupModel] = field(default_factory=list)
    add_actions: list[AddActionModel] = field(default_factory=list)
    zorders: list[ZOrderModel] = field(default_factory=list)
    button_groups: list[ButtonGroupModel] = field(default_factory=list)
    unknown_top_level_xml: list[str] = field(default_factory=list)

    def collect_object_names(self) -> list[str]:
        """Collect all object names in model traversal order."""
        return self.root_widget.collect_object_names()

    def duplicate_object_names(self) -> list[str]:
        """Return duplicate object names in deterministic sorted order."""
        counts = Counter(self.collect_object_names())
        duplicates = [name for name, count in counts.items() if count > 1]
        duplicates.sort()
        return duplicates

