"""Live document nodes: the read API (CONTRACTS.md section 2.2).

Nodes are owned by one ``UiDocument``. Outside ``engine.ui4.mutate`` they are
read-only: every accessor returns immutable data (str, int, tuples, frozen
values, or other nodes). Holding a node across a command is allowed but the
holder must re-resolve by id after any ChangeSet that removes it
(``UiDocument.contains``).
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import Value


class Node:
    """Common read API for every node kind."""

    @property
    def id(self) -> NodeId:
        ...

    @property
    def kind(self) -> str:
        """A ``schema.NodeKind``."""
        ...

    @property
    def parent_id(self) -> Optional[NodeId]:
        """None only for the ``ui`` node."""
        ...

    @property
    def parent_slot(self) -> Optional[str]:
        """The slot of the parent this node sits in."""
        ...

    def index_in_parent(self) -> int:
        """Position in the parent's slot list. O(siblings)."""
        ...

    def field(self, name: str) -> object:
        """Field value (None when unset). KeyError for a name the kind lacks."""
        ...

    def children(self, slot: str) -> Tuple["Node", ...]:
        """Children in ``slot``. KeyError for a slot the kind lacks."""
        ...

    def properties(self) -> Tuple[PropertyEntry, ...]:
        """``<property>`` entries in document order (empty for kinds without them)."""
        ...

    def attributes(self) -> Tuple[PropertyEntry, ...]:
        """``<attribute>`` entries in document order."""
        ...

    def prop(self, name: str) -> Optional[PropertyEntry]:
        """The ``<property>`` named ``name`` or None. O(1) (per-node name map)."""
        ...

    def attr(self, name: str) -> Optional[PropertyEntry]:
        """The ``<attribute>`` named ``name`` or None. O(1)."""
        ...

    def value(self, name: str) -> Optional[Value]:
        """Shortcut for ``prop(name).value``."""
        ...

    def extra_attrs(self) -> Tuple[Tuple[str, str], ...]:
        """Unknown XML attributes, input order."""
        ...

    def opaque(self) -> Tuple["OpaqueNode", ...]:
        """Unknown child elements preserved at this node."""
        ...

    def to_spec(self) -> NodeSpec:
        """Frozen snapshot of this subtree, ids included. O(subtree)."""
        ...


class WidgetNode(Node):
    @property
    def class_name(self) -> str:
        ...

    @property
    def object_name(self) -> str:
        ...

    @property
    def layout(self) -> Optional["LayoutNode"]:
        ...

    @property
    def child_widgets(self) -> Tuple["WidgetNode", ...]:
        """The ``children`` slot (direct ``<widget>`` children; pages of a
        QTabWidget/QStackedWidget/QToolBox, panes of a QSplitter, the viewport
        child of a QScrollArea, main-window parts)."""
        ...

    @property
    def zorder(self) -> Tuple[str, ...]:
        ...


class LayoutNode(Node):
    @property
    def class_name(self) -> str:
        """``QVBoxLayout``, ``QHBoxLayout``, ``QGridLayout``, ``QFormLayout`` or a
        custom layout class."""
        ...

    @property
    def object_name(self) -> str:
        ...

    @property
    def items(self) -> Tuple["LayoutItemNode", ...]:
        ...

    def owner_widget_id(self) -> Optional[NodeId]:
        """The widget whose ``layout`` slot holds this layout, or None for a
        nested layout (inside a layout item)."""
        ...


class LayoutItemNode(Node):
    @property
    def row(self) -> Optional[int]:
        ...

    @property
    def column(self) -> Optional[int]:
        ...

    @property
    def rowspan(self) -> Optional[int]:
        ...

    @property
    def colspan(self) -> Optional[int]:
        ...

    @property
    def alignment(self) -> Optional[str]:
        ...

    @property
    def content(self) -> Optional[Node]:
        """WidgetNode, LayoutNode, SpacerNode or None (an empty cell)."""
        ...


class SpacerNode(Node):
    @property
    def name(self) -> str:
        ...


class ActionNode(Node):
    @property
    def name(self) -> str:
        ...

    @property
    def menu(self) -> Optional[str]:
        ...


class ActionGroupNode(Node):
    @property
    def name(self) -> str:
        ...


class ActionRefNode(Node):
    """``<addaction name=".."/>``. ``name`` is an action, a menu widget, or
    ``separator``."""

    @property
    def name(self) -> str:
        ...


class ItemNode(Node):
    """A list/combo/tree/table widget item. ``row``/``column`` only on table cells."""


class HeaderNode(Node):
    """A table/tree header section. ``axis`` is ``"row"`` or ``"column"``."""


class ButtonGroupNode(Node):
    @property
    def name(self) -> str:
        ...


class ConnectionNode(Node):
    @property
    def sender(self) -> str:
        ...

    @property
    def signal(self) -> str:
        ...

    @property
    def receiver(self) -> str:
        ...

    @property
    def slot(self) -> str:
        ...


class CustomWidgetNode(Node):
    @property
    def class_name(self) -> str:
        ...

    @property
    def extends(self) -> str:
        ...


class IncludeNode(Node):
    """``<includes><include location=".." impldecl="..">text</include>``."""


class ResourceNode(Node):
    """``<resources><include location="x.qrc"/>``."""

    @property
    def location(self) -> str:
        ...


class OpaqueNode(Node):
    """An unknown element preserved at a known position."""

    @property
    def element(self) -> OpaqueElement:
        ...

    @property
    def anchor(self) -> Tuple[str, int]:
        """``(group, n)``: written after the n-th typed entry of write-order group
        ``group`` (an earlier duplicate property stays earlier). ``("", 0)`` = first."""
        ...
