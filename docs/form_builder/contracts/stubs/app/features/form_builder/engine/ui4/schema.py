"""The typed ui4 node schema (CONTRACTS.md section 2.2).

This table is the single source of truth for node kinds, their scalar fields,
their child slots, which kinds each slot accepts, and the XML write order. The
reader, writer, mutation primitives, validator and realize all read it. A new
ui4 construct is added here first.

Write order follows the ui4.xsd ``xs:sequence`` of each element, which is the
order Qt Designer's serializer emits. The M0.4b Designer-resave corpus is the
oracle for that claim; if the corpus disagrees, the corpus wins and this table
changes (with a test).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Literal, Optional, Tuple

NodeKind = Literal[
    "ui",            # the document; id DOCUMENT_ID
    "widget",
    "layout",
    "layoutitem",    # <item> inside <layout>: one cell
    "spacer",
    "action",
    "actiongroup",
    "actionref",     # <addaction name=".."/>
    "item",          # <item> of a list/combo/tree/table widget
    "header",        # <row>/<column> of a table/tree widget (field "axis")
    "buttongroup",
    "connection",
    "customwidget",
    "include",       # <includes><include>
    "resource",      # <resources><include location=".."/>
    "opaque",        # unknown element at a known position
]

SlotName = Literal[
    # ui
    "root", "customwidgets", "includes", "resources", "connections",
    "buttongroups",
    # widget
    "rows", "columns", "items", "layout", "children", "actions",
    "action_groups", "add_actions",
    # layout
    "layout_items",
    # layoutitem
    "content",
    # item (nested items), actiongroup reuse "actions"/"action_groups"
    "subitems",
    # every element kind that can carry unknown children
    "opaque",
]

PropertyKind = Literal["property", "attribute"]


@dataclass(frozen=True)
class SlotSpec:
    """One ordered child list of a node kind.

    ``accepts``: node kinds allowed in the slot.
    ``max_len``: 1 for single-child slots (``root``, ``layout``, ``content``), else 0
    meaning unbounded.
    ``element``: the XML element name the children are written as (for kinds whose
    tag depends on the slot, such as header rows vs columns).
    ``wrapper``: for document-level containers, the wrapper element
    (``connections``, ``customwidgets``...) or "" for inline children.
    """

    name: str
    accepts: FrozenSet[str]
    max_len: int = 0
    element: str = ""
    wrapper: str = ""


@dataclass(frozen=True)
class FieldSpec:
    """A scalar field. ``xml`` says where it lives: ``attr:<name>`` (an XML attribute),
    ``text`` (element text), ``child:<tag>`` (text of a child element), or
    ``derived`` (not written; computed). Field values are immutable: str, int,
    bool, None, tuples of those, or frozen dataclasses from this package."""

    name: str
    xml: str
    required: bool = False


@dataclass(frozen=True)
class KindSpec:
    kind: str
    element: str
    fields: Tuple[FieldSpec, ...]
    slots: Tuple[SlotSpec, ...]
    #: Whether the kind carries <property> entries, <attribute> entries.
    has_properties: bool = False
    has_attributes: bool = False
    #: Full write order of the element's content: group names, where a group is
    #: "properties", "attributes", a slot name, or a "child:<tag>" field. Opaque
    #: children are written at ``OpaqueNode.anchor = (group, n)``: after the n-th
    #: typed entry of ``group`` (at the group's end if it now has fewer); group
    #: "" means before the first group.
    write_order: Tuple[str, ...] = ()
    #: XML attribute write order for known attributes. Unknown attributes are
    #: written after these, in input order.
    attr_order: Tuple[str, ...] = ()


#: The schema. Implementations fill every kind listed in NodeKind; the stub shows
#: the two that drive most of the contract. Field names here are the names used
#: by SetFieldOp and FieldChanged.
SCHEMA: Dict[str, KindSpec] = {
    "ui": KindSpec(
        kind="ui",
        element="ui",
        fields=(
            FieldSpec("version", "attr:version"),
            FieldSpec("language", "attr:language"),
            FieldSpec("displayname", "attr:displayname"),
            FieldSpec("idbasedtr", "attr:idbasedtr"),
            FieldSpec("label", "attr:label"),
            FieldSpec("connectslotsbyname", "attr:connectslotsbyname"),
            FieldSpec("stdsetdef", "attr:stdsetdef"),
            FieldSpec("stdSetDef", "attr:stdSetDef"),
            FieldSpec("author", "child:author"),
            FieldSpec("comment", "child:comment"),
            FieldSpec("exportmacro", "child:exportmacro"),
            FieldSpec("class_name", "child:class"),
            # LayoutDefault(spacing, margin) or None
            FieldSpec("layoutdefault", "child:layoutdefault"),
            # LayoutFunction(spacing, margin) or None
            FieldSpec("layoutfunction", "child:layoutfunction"),
            # str or None (function name text)
            FieldSpec("pixmapfunction", "child:pixmapfunction"),
            # Tuple[str, ...] or None (None = no <tabstops> element)
            FieldSpec("tabstops", "child:tabstops"),
            # SlotsDecl or None
            FieldSpec("form_slots", "child:slots"),
            # OpaqueElement or None: <designerdata> and <images> are kept verbatim
            FieldSpec("designerdata", "child:designerdata"),
            FieldSpec("images", "child:images"),
            # FrozenSet[str] of wrapper elements present even when empty
            # ("customwidgets", "includes", "resources", "connections", "buttongroups")
            FieldSpec("present_wrappers", "derived"),
        ),
        slots=(
            SlotSpec("root", frozenset({"widget"}), max_len=1, element="widget"),
            SlotSpec("customwidgets", frozenset({"customwidget"}), element="customwidget", wrapper="customwidgets"),
            SlotSpec("includes", frozenset({"include"}), element="include", wrapper="includes"),
            SlotSpec("resources", frozenset({"resource"}), element="include", wrapper="resources"),
            SlotSpec("connections", frozenset({"connection"}), element="connection", wrapper="connections"),
            SlotSpec("buttongroups", frozenset({"buttongroup"}), element="buttongroup", wrapper="buttongroups"),
            SlotSpec("opaque", frozenset({"opaque"})),
        ),
        write_order=(
            "child:author", "child:comment", "child:exportmacro", "child:class",
            "root", "child:layoutdefault", "child:layoutfunction",
            "child:pixmapfunction", "customwidgets", "child:tabstops",
            "child:images", "includes", "resources", "connections",
            "child:designerdata", "child:slots", "buttongroups",
        ),
        attr_order=(
            "version", "language", "displayname", "idbasedtr", "label",
            "connectslotsbyname", "stdsetdef", "stdSetDef",
        ),
    ),
    "widget": KindSpec(
        kind="widget",
        element="widget",
        fields=(
            FieldSpec("class_name", "attr:class", required=True),
            FieldSpec("object_name", "attr:name", required=True),
            FieldSpec("native", "attr:native"),
            # Tuple[str, ...]: <zorder> names in order
            FieldSpec("zorder", "child:zorder"),
        ),
        slots=(
            SlotSpec("rows", frozenset({"header"}), element="row"),
            SlotSpec("columns", frozenset({"header"}), element="column"),
            SlotSpec("items", frozenset({"item"}), element="item"),
            SlotSpec("layout", frozenset({"layout"}), max_len=1, element="layout"),
            SlotSpec("children", frozenset({"widget"}), element="widget"),
            SlotSpec("actions", frozenset({"action"}), element="action"),
            SlotSpec("action_groups", frozenset({"actiongroup"}), element="actiongroup"),
            SlotSpec("add_actions", frozenset({"actionref"}), element="addaction"),
            SlotSpec("opaque", frozenset({"opaque"})),
        ),
        has_properties=True,
        has_attributes=True,
        write_order=(
            "properties", "attributes", "rows", "columns", "items", "layout",
            "children", "actions", "action_groups", "add_actions", "child:zorder",
        ),
        attr_order=("class", "name", "native"),
    ),
    # "layout": fields class_name, object_name, stretch, rowstretch, columnstretch,
    #     rowminimumheight, columnminimumwidth (raw comma lists, Optional[str]);
    #     properties; slot layout_items; write_order ("properties", "layout_items");
    #     attr_order ("class", "name", "stretch", "rowstretch", "columnstretch",
    #     "rowminimumheight", "columnminimumwidth").
    # "layoutitem": fields row, column, rowspan, colspan (Optional[int]),
    #     alignment (Optional[str]); slot content (max 1: widget|layout|spacer);
    #     attr_order ("row", "column", "rowspan", "colspan", "alignment").
    # "spacer": field name; properties.
    # "action": fields name, menu; properties, attributes.
    # "actiongroup": field name; properties, attributes; slots actions, action_groups.
    # "actionref": field name.
    # "item": fields row, column (Optional[int]); properties; slot subitems.
    # "header": field axis ("row"|"column", derived from slot); properties.
    # "buttongroup": field name; properties, attributes.
    # "connection": fields sender, signal, receiver, slot (str), hints
    #     (Tuple[ConnectionHint, ...] or None when <hints> absent).
    # "customwidget": fields class_name, extends, header (HeaderDecl or None),
    #     sizehint (SizeValue or None), addpagemethod, container (Optional[int]),
    #     pixmap, slots (SlotsDecl or None), propertyspecifications (OpaqueElement
    #     or None); deprecated children (script, properties, sizepolicy) go to
    #     the opaque slot.
    # "include": fields location, impldecl, text.
    # "resource": field location.
    # "opaque": fields element (OpaqueElement), anchor (Tuple[str, int]: the
    #     write_order group it sits in or follows, and the number of typed
    #     entries of that group before it; ("", 0) for first).
}


@dataclass(frozen=True)
class LayoutDefault:
    """``<layoutdefault spacing=".." margin=".."/>``. Absent attribute = None."""

    spacing: Optional[int] = None
    margin: Optional[int] = None


@dataclass(frozen=True)
class LayoutFunction:
    """``<layoutfunction spacing=".." margin=".."/>``: function names."""

    spacing: Optional[str] = None
    margin: Optional[str] = None


@dataclass(frozen=True)
class SlotsDecl:
    """``<slots>`` on the form or a custom widget: signatures as written,
    ``signals`` before ``slots`` in write order."""

    signals: Tuple[str, ...] = ()
    slots: Tuple[str, ...] = ()


@dataclass(frozen=True)
class HeaderDecl:
    """Custom widget ``<header location="global|local">text</header>``."""

    text: str
    location: Optional[str] = None


@dataclass(frozen=True)
class ConnectionHint:
    """``<hint type="sourcelabel"><x>..</x><y>..</y></hint>``."""

    type: str
    x: int
    y: int
