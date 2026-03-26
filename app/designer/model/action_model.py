"""Action graph models for advanced `.ui` contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from app.designer.model.property_value import PropertyValue


@dataclass(frozen=True)
class AddActionModel:
    """Represents one `<addaction name=\"...\"/>` placement reference."""

    name: str


@dataclass(frozen=True)
class ZOrderModel:
    """Represents one `<zorder>...</zorder>` ordering entry."""

    name: str


@dataclass
class ButtonGroupModel:
    """Represents one `<buttongroup>` definition."""

    name: str
    exclusive: bool | None = None
    unknown_children_xml: list[str] = field(default_factory=list)


@dataclass
class ActionModel:
    """Represents one `<action>` definition."""

    name: str
    properties: dict[str, PropertyValue] = field(default_factory=dict)
    add_actions: list[AddActionModel] = field(default_factory=list)
    unknown_children_xml: list[str] = field(default_factory=list)


@dataclass
class ActionGroupModel:
    """Represents one `<actiongroup>` definition."""

    name: str
    properties: dict[str, PropertyValue] = field(default_factory=dict)
    add_actions: list[AddActionModel] = field(default_factory=list)
    unknown_children_xml: list[str] = field(default_factory=list)


DesignerActionNode = Union[ActionModel, ActionGroupModel]
