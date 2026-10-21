"""Live document nodes: the read API (CONTRACTS.md section 2.2).

Nodes are owned by one ``UiDocument``. Outside ``engine.ui4.mutate`` they are
read-only: every accessor returns immutable data (str, int, tuples, frozen
values, or other nodes). Holding a node across a command is allowed but the
holder must re-resolve by id after any ChangeSet that removes it
(``UiDocument.contains``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.schema import SCHEMA

_FIELD_NAMES = {
    kind: frozenset(item.name for item in spec.fields) for kind, spec in SCHEMA.items()
}
_SLOT_NAMES = {
    kind: frozenset(item.name for item in spec.slots) for kind, spec in SCHEMA.items()
}
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import Value


@dataclass(frozen=True)
class Node:
    """Common read API for every node kind."""

    node_id: NodeId
    node_kind: str
    parent_id: Optional[NodeId]
    parent_slot_name: Optional[str]
    slot_index: int
    fields: Tuple[Tuple[str, object], ...]
    prop_entries: Tuple[PropertyEntry, ...]
    attr_entries: Tuple[PropertyEntry, ...]
    slots: Tuple[Tuple[str, Tuple["Node", ...]], ...]
    unknown_attrs: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "_fields_by_name", dict(self.fields))
        object.__setattr__(self, "_props_by_name", {entry.name: entry for entry in self.prop_entries})
        object.__setattr__(self, "_attrs_by_name", {entry.name: entry for entry in self.attr_entries})
        object.__setattr__(self, "_slots_by_name", dict(self.slots))

    @property
    def id(self) -> NodeId:
        return self.node_id

    @property
    def kind(self) -> str:
        """A ``schema.NodeKind``."""
        return self.node_kind

    @property
    def parent_slot(self) -> Optional[str]:
        """The slot of the parent this node sits in."""
        return self.parent_slot_name

    def index_in_parent(self) -> int:
        """Position in the parent's slot list. O(siblings)."""
        return self.slot_index

    def field(self, name: str) -> object:
        """Field value (None when unset). KeyError for a name the kind lacks."""
        if name not in _FIELD_NAMES[self.kind]:
            raise KeyError(name)
        return self._field_map().get(name)

    def children(self, slot: str) -> Tuple["Node", ...]:
        """Children in ``slot``. KeyError for a slot the kind lacks."""
        if slot not in _SLOT_NAMES[self.kind]:
            raise KeyError(slot)
        found = self._slot_map().get(slot)
        if found is None:
            return ()
        return found

    def properties(self) -> Tuple[PropertyEntry, ...]:
        """``<property>`` entries in document order (empty for kinds without them)."""
        return self.prop_entries

    def attributes(self) -> Tuple[PropertyEntry, ...]:
        """``<attribute>`` entries in document order."""
        return self.attr_entries

    def prop(self, name: str) -> Optional[PropertyEntry]:
        """The ``<property>`` named ``name`` or None. O(1) (per-node name map)."""
        return self._prop_map().get(name)

    def attr(self, name: str) -> Optional[PropertyEntry]:
        """The ``<attribute>`` named ``name`` or None. O(1)."""
        return self._attr_map().get(name)

    def value(self, name: str) -> Optional[Value]:
        """Shortcut for ``prop(name).value``."""
        entry = self.prop(name)
        if entry is None:
            return None
        return entry.value

    def extra_attrs(self) -> Tuple[Tuple[str, str], ...]:
        """Unknown XML attributes, input order."""
        return self.unknown_attrs

    def opaque(self) -> Tuple["OpaqueNode", ...]:
        """Unknown child elements preserved at this node."""
        if "opaque" not in _SLOT_NAMES[self.kind]:
            return ()
        return tuple(child for child in self.children("opaque") if isinstance(child, OpaqueNode))

    def to_spec(self) -> NodeSpec:
        """Frozen snapshot of this subtree, ids included. O(subtree)."""
        return NodeSpec(
            kind=self.kind,
            id=self.id,
            fields=self.fields,
            properties=self.prop_entries,
            attributes=self.attr_entries,
            slots=tuple(
                (name, tuple(child.to_spec() for child in kids))
                for name, kids in self.slots
            ),
            extra_attrs=self.unknown_attrs,
        )

    def _field_map(self) -> Dict[str, object]:
        return object.__getattribute__(self, "_fields_by_name")

    def _prop_map(self) -> Dict[str, PropertyEntry]:
        return object.__getattribute__(self, "_props_by_name")

    def _attr_map(self) -> Dict[str, PropertyEntry]:
        return object.__getattribute__(self, "_attrs_by_name")

    def _slot_map(self) -> Dict[str, Tuple["Node", ...]]:
        return object.__getattribute__(self, "_slots_by_name")


def _text_field(node: Node, name: str) -> str:
    value = node.field(name)
    if isinstance(value, str):
        return value
    return ""


class WidgetNode(Node):
    @property
    def class_name(self) -> str:
        return _text_field(self, "class_name")

    @property
    def object_name(self) -> str:
        return _text_field(self, "object_name")

    @property
    def layout(self) -> Optional["LayoutNode"]:
        kids = self.children("layout")
        if not kids:
            return None
        child = kids[0]
        if isinstance(child, LayoutNode):
            return child
        return None

    @property
    def child_widgets(self) -> Tuple["WidgetNode", ...]:
        """The ``children`` slot (direct ``<widget>`` children; pages of a
        QTabWidget/QStackedWidget/QToolBox, panes of a QSplitter, the viewport
        child of a QScrollArea, main-window parts)."""
        return tuple(child for child in self.children("children") if isinstance(child, WidgetNode))

    @property
    def zorder(self) -> Tuple[str, ...]:
        value = self.field("zorder")
        if isinstance(value, tuple):
            return tuple(item for item in value if isinstance(item, str))
        return ()


class LayoutNode(Node):
    @property
    def class_name(self) -> str:
        """``QVBoxLayout``, ``QHBoxLayout``, ``QGridLayout``, ``QFormLayout`` or a
        custom layout class."""
        return _text_field(self, "class_name")

    @property
    def object_name(self) -> str:
        return _text_field(self, "object_name")

    @property
    def items(self) -> Tuple["LayoutItemNode", ...]:
        return tuple(child for child in self.children("layout_items") if isinstance(child, LayoutItemNode))

    def owner_widget_id(self) -> Optional[NodeId]:
        """The widget whose ``layout`` slot holds this layout, or None for a
        nested layout (inside a layout item)."""
        if self.parent_slot == "layout":
            return self.parent_id
        return None


class LayoutItemNode(Node):
    @property
    def row(self) -> Optional[int]:
        return _optional_int(self, "row")

    @property
    def column(self) -> Optional[int]:
        return _optional_int(self, "column")

    @property
    def rowspan(self) -> Optional[int]:
        return _optional_int(self, "rowspan")

    @property
    def colspan(self) -> Optional[int]:
        return _optional_int(self, "colspan")

    @property
    def alignment(self) -> Optional[str]:
        value = self.field("alignment")
        if isinstance(value, str):
            return value
        return None

    @property
    def content(self) -> Optional[Node]:
        """WidgetNode, LayoutNode, SpacerNode or None (an empty cell)."""
        kids = self.children("content")
        if not kids:
            return None
        return kids[0]


class SpacerNode(Node):
    @property
    def name(self) -> str:
        return _text_field(self, "name")


class ActionNode(Node):
    @property
    def name(self) -> str:
        return _text_field(self, "name")

    @property
    def menu(self) -> Optional[str]:
        value = self.field("menu")
        if isinstance(value, str):
            return value
        return None


class ActionGroupNode(Node):
    @property
    def name(self) -> str:
        return _text_field(self, "name")


class ActionRefNode(Node):
    """``<addaction name=".."/>``. ``name`` is an action, a menu widget, or
    ``separator``."""

    @property
    def name(self) -> str:
        return _text_field(self, "name")


class ItemNode(Node):
    """A list/combo/tree/table widget item. ``row``/``column`` only on table cells."""

    @property
    def row(self) -> Optional[int]:
        return _optional_int(self, "row")

    @property
    def column(self) -> Optional[int]:
        return _optional_int(self, "column")


class HeaderNode(Node):
    """A table/tree header section. ``axis`` is ``"row"`` or ``"column"``."""

    @property
    def axis(self) -> str:
        return _text_field(self, "axis")


class ButtonGroupNode(Node):
    @property
    def name(self) -> str:
        return _text_field(self, "name")


class ConnectionNode(Node):
    @property
    def sender(self) -> str:
        return _text_field(self, "sender")

    @property
    def signal(self) -> str:
        return _text_field(self, "signal")

    @property
    def receiver(self) -> str:
        return _text_field(self, "receiver")

    @property
    def slot(self) -> str:
        return _text_field(self, "slot")


class CustomWidgetNode(Node):
    @property
    def class_name(self) -> str:
        return _text_field(self, "class_name")

    @property
    def extends(self) -> str:
        return _text_field(self, "extends")


class IncludeNode(Node):
    """``<includes><include location=".." impldecl="..">text</include>``."""


class ResourceNode(Node):
    """``<resources><include location="x.qrc"/>``."""

    @property
    def location(self) -> str:
        return _text_field(self, "location")


class OpaqueNode(Node):
    """An unknown element preserved at a known position."""

    @property
    def element(self) -> OpaqueElement:
        value = self.field("element")
        if isinstance(value, OpaqueElement):
            return value
        raise TypeError("opaque node is missing its element")

    @property
    def anchor(self) -> str:
        """The write-order group this element followed in the input ("" = first)."""
        return _text_field(self, "anchor")


_KIND_CLASS = {
    "ui": Node,
    "widget": WidgetNode,
    "layout": LayoutNode,
    "layoutitem": LayoutItemNode,
    "spacer": SpacerNode,
    "action": ActionNode,
    "actiongroup": ActionGroupNode,
    "actionref": ActionRefNode,
    "item": ItemNode,
    "header": HeaderNode,
    "buttongroup": ButtonGroupNode,
    "connection": ConnectionNode,
    "customwidget": CustomWidgetNode,
    "include": IncludeNode,
    "resource": ResourceNode,
    "opaque": OpaqueNode,
}


def build_node(
    kind: str,
    node_id: NodeId,
    parent_id: Optional[NodeId],
    parent_slot: Optional[str],
    slot_index: int,
    fields: Tuple[Tuple[str, object], ...],
    properties: Tuple[PropertyEntry, ...] = (),
    attributes: Tuple[PropertyEntry, ...] = (),
    slots: Tuple[Tuple[str, Tuple[Node, ...]], ...] = (),
    extra_attrs: Tuple[Tuple[str, str], ...] = (),
) -> Node:
    cls = _KIND_CLASS[kind]
    return cls(
        node_id=node_id,
        node_kind=kind,
        parent_id=parent_id,
        parent_slot_name=parent_slot,
        slot_index=slot_index,
        fields=fields,
        prop_entries=properties,
        attr_entries=attributes,
        slots=slots,
        unknown_attrs=extra_attrs,
    )


def placed(node: Node, parent_id: Optional[NodeId], parent_slot: Optional[str], slot_index: int) -> Node:
    """Same subtree with a new parent link. Descendants are shared."""
    if node.parent_id == parent_id and node.parent_slot_name == parent_slot and node.slot_index == slot_index:
        return node
    return replace(node, parent_id=parent_id, parent_slot_name=parent_slot, slot_index=slot_index)


def with_slots(node: Node, slots: Tuple[Tuple[str, Tuple[Node, ...]], ...]) -> Node:
    return replace(node, slots=slots)


def with_fields(node: Node, fields: Tuple[Tuple[str, object], ...]) -> Node:
    return replace(node, fields=fields)


def with_properties(node: Node, properties: Tuple[PropertyEntry, ...]) -> Node:
    return replace(node, prop_entries=properties)


def with_attributes(node: Node, attributes: Tuple[PropertyEntry, ...]) -> Node:
    return replace(node, attr_entries=attributes)


def _optional_int(node: Node, name: str) -> Optional[int]:
    value = node.field(name)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
