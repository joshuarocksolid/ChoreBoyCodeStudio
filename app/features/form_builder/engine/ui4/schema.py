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

from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.values import SizeValue

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


def _opaque_slot() -> SlotSpec:
    return SlotSpec("opaque", frozenset({"opaque"}))


#: The schema. Field names here are the names used by SetFieldOp and FieldChanged.
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
            FieldSpec("layoutdefault", "child:layoutdefault"),
            FieldSpec("layoutfunction", "child:layoutfunction"),
            FieldSpec("pixmapfunction", "child:pixmapfunction"),
            FieldSpec("tabstops", "child:tabstops"),
            FieldSpec("form_slots", "child:slots"),
            FieldSpec("designerdata", "child:designerdata"),
            FieldSpec("images", "child:images"),
            FieldSpec("present_wrappers", "derived"),
        ),
        slots=(
            SlotSpec("root", frozenset({"widget"}), max_len=1, element="widget"),
            SlotSpec("customwidgets", frozenset({"customwidget"}), element="customwidget", wrapper="customwidgets"),
            SlotSpec("includes", frozenset({"include"}), element="include", wrapper="includes"),
            SlotSpec("resources", frozenset({"resource"}), element="include", wrapper="resources"),
            SlotSpec("connections", frozenset({"connection"}), element="connection", wrapper="connections"),
            SlotSpec("buttongroups", frozenset({"buttongroup"}), element="buttongroup", wrapper="buttongroups"),
            _opaque_slot(),
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
            _opaque_slot(),
        ),
        has_properties=True,
        has_attributes=True,
        write_order=(
            "properties", "attributes", "rows", "columns", "items", "layout",
            "children", "actions", "action_groups", "add_actions", "child:zorder",
        ),
        attr_order=("class", "name", "native"),
    ),
    "layout": KindSpec(
        kind="layout",
        element="layout",
        fields=(
            FieldSpec("class_name", "attr:class", required=True),
            FieldSpec("object_name", "attr:name", required=True),
            FieldSpec("stretch", "attr:stretch"),
            FieldSpec("rowstretch", "attr:rowstretch"),
            FieldSpec("columnstretch", "attr:columnstretch"),
            FieldSpec("rowminimumheight", "attr:rowminimumheight"),
            FieldSpec("columnminimumwidth", "attr:columnminimumwidth"),
        ),
        slots=(
            SlotSpec("layout_items", frozenset({"layoutitem"}), element="item"),
            _opaque_slot(),
        ),
        has_properties=True,
        write_order=("properties", "layout_items"),
        attr_order=(
            "class", "name", "stretch", "rowstretch", "columnstretch",
            "rowminimumheight", "columnminimumwidth",
        ),
    ),
    "layoutitem": KindSpec(
        kind="layoutitem",
        element="item",
        fields=(
            FieldSpec("row", "attr:row"),
            FieldSpec("column", "attr:column"),
            FieldSpec("rowspan", "attr:rowspan"),
            FieldSpec("colspan", "attr:colspan"),
            FieldSpec("alignment", "attr:alignment"),
        ),
        slots=(
            SlotSpec("content", frozenset({"widget", "layout", "spacer"}), max_len=1),
            _opaque_slot(),
        ),
        write_order=("content",),
        attr_order=("row", "column", "rowspan", "colspan", "alignment"),
    ),
    "spacer": KindSpec(
        kind="spacer",
        element="spacer",
        fields=(FieldSpec("name", "attr:name", required=True),),
        slots=(_opaque_slot(),),
        has_properties=True,
        write_order=("properties",),
        attr_order=("name",),
    ),
    "action": KindSpec(
        kind="action",
        element="action",
        fields=(
            FieldSpec("name", "attr:name", required=True),
            FieldSpec("menu", "attr:menu"),
        ),
        slots=(_opaque_slot(),),
        has_properties=True,
        has_attributes=True,
        write_order=("properties", "attributes"),
        attr_order=("name", "menu"),
    ),
    "actiongroup": KindSpec(
        kind="actiongroup",
        element="actiongroup",
        fields=(FieldSpec("name", "attr:name", required=True),),
        slots=(
            SlotSpec("actions", frozenset({"action"}), element="action"),
            SlotSpec("action_groups", frozenset({"actiongroup"}), element="actiongroup"),
            _opaque_slot(),
        ),
        has_properties=True,
        has_attributes=True,
        write_order=("actions", "action_groups", "properties", "attributes"),
        attr_order=("name",),
    ),
    "actionref": KindSpec(
        kind="actionref",
        element="addaction",
        fields=(FieldSpec("name", "attr:name", required=True),),
        slots=(_opaque_slot(),),
        attr_order=("name",),
    ),
    "item": KindSpec(
        kind="item",
        element="item",
        fields=(
            FieldSpec("row", "attr:row"),
            FieldSpec("column", "attr:column"),
        ),
        slots=(
            SlotSpec("subitems", frozenset({"item"}), element="item"),
            _opaque_slot(),
        ),
        has_properties=True,
        write_order=("properties", "subitems"),
        attr_order=("row", "column"),
    ),
    "header": KindSpec(
        kind="header",
        element="",
        fields=(FieldSpec("axis", "derived", required=True),),
        slots=(_opaque_slot(),),
        has_properties=True,
        write_order=("properties",),
    ),
    "buttongroup": KindSpec(
        kind="buttongroup",
        element="buttongroup",
        fields=(FieldSpec("name", "attr:name", required=True),),
        slots=(_opaque_slot(),),
        has_properties=True,
        has_attributes=True,
        write_order=("properties", "attributes"),
        attr_order=("name",),
    ),
    "connection": KindSpec(
        kind="connection",
        element="connection",
        fields=(
            FieldSpec("sender", "child:sender", required=True),
            FieldSpec("signal", "child:signal", required=True),
            FieldSpec("receiver", "child:receiver", required=True),
            FieldSpec("slot", "child:slot", required=True),
            FieldSpec("hints", "child:hints"),
        ),
        slots=(_opaque_slot(),),
        write_order=(
            "child:sender", "child:signal", "child:receiver", "child:slot", "child:hints",
        ),
    ),
    "customwidget": KindSpec(
        kind="customwidget",
        element="customwidget",
        fields=(
            FieldSpec("class_name", "child:class", required=True),
            FieldSpec("extends", "child:extends", required=True),
            FieldSpec("header", "child:header"),
            FieldSpec("sizehint", "child:sizehint"),
            FieldSpec("addpagemethod", "child:addpagemethod"),
            FieldSpec("container", "child:container"),
            FieldSpec("pixmap", "child:pixmap"),
            FieldSpec("slots", "child:slots"),
            FieldSpec("propertyspecifications", "child:propertyspecifications"),
        ),
        slots=(_opaque_slot(),),
        write_order=(
            "child:class", "child:extends", "child:header", "child:sizehint",
            "child:addpagemethod", "child:container", "child:pixmap",
            "child:slots", "child:propertyspecifications",
        ),
    ),
    "include": KindSpec(
        kind="include",
        element="include",
        fields=(
            FieldSpec("location", "attr:location"),
            FieldSpec("impldecl", "attr:impldecl"),
            FieldSpec("text", "text"),
        ),
        slots=(_opaque_slot(),),
        attr_order=("location", "impldecl"),
    ),
    "resource": KindSpec(
        kind="resource",
        element="include",
        fields=(FieldSpec("location", "attr:location", required=True),),
        slots=(_opaque_slot(),),
        attr_order=("location",),
    ),
    "opaque": KindSpec(
        kind="opaque",
        element="",
        fields=(
            FieldSpec("element", "derived", required=True),
            # (group, n): write_order group, and how many typed entries of that
            # group came before this node. ("", 0) is before the first group.
            FieldSpec("anchor", "derived", required=True),
        ),
        slots=(),
    ),
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


def slot_spec(kind: str, name: str) -> SlotSpec:
    for item in SCHEMA[kind].slots:
        if item.name == name:
            return item
    raise KeyError(name)


def field_spec(kind: str, name: str) -> FieldSpec:
    for item in SCHEMA[kind].fields:
        if item.name == name:
            return item
    raise KeyError(name)


_STR = (str,)
_INT = (int,)
_TEXT = (str, OpaqueElement)

#: Declared Python types for invariant 6. ``None`` means the field is unset.
FIELD_TYPES: Dict[Tuple[str, str], Tuple[type, ...]] = {}
for _kind, _names in (
    ("ui", ("version", "language", "displayname", "idbasedtr", "label", "connectslotsbyname", "stdsetdef", "stdSetDef")),
    ("widget", ("class_name", "object_name", "native")),
    ("layout", ("class_name", "object_name", "stretch", "rowstretch", "columnstretch", "rowminimumheight", "columnminimumwidth")),
    ("layoutitem", ("alignment",)),
    ("spacer", ("name",)),
    ("action", ("name", "menu")),
    ("actiongroup", ("name",)),
    ("actionref", ("name",)),
    ("header", ("axis",)),
    ("buttongroup", ("name",)),
    ("include", ("location", "impldecl", "text")),
    ("resource", ("location",)),
):
    for _name in _names:
        FIELD_TYPES[(_kind, _name)] = _STR
for _kind, _names in (
    ("layoutitem", ("row", "column", "rowspan", "colspan")),
    ("item", ("row", "column")),
):
    for _name in _names:
        FIELD_TYPES[(_kind, _name)] = _INT
for _name in ("author", "comment", "exportmacro", "class_name", "pixmapfunction"):
    FIELD_TYPES[("ui", _name)] = _TEXT
for _name in ("class_name", "extends", "addpagemethod", "pixmap"):
    FIELD_TYPES[("customwidget", _name)] = _TEXT
for _name in ("sender", "signal", "receiver", "slot"):
    FIELD_TYPES[("connection", _name)] = _TEXT
FIELD_TYPES[("ui", "layoutdefault")] = (LayoutDefault, OpaqueElement)
FIELD_TYPES[("ui", "layoutfunction")] = (LayoutFunction, OpaqueElement)
FIELD_TYPES[("ui", "tabstops")] = (tuple, OpaqueElement)
FIELD_TYPES[("ui", "form_slots")] = (SlotsDecl, OpaqueElement)
FIELD_TYPES[("ui", "designerdata")] = (OpaqueElement,)
FIELD_TYPES[("ui", "images")] = (OpaqueElement,)
FIELD_TYPES[("ui", "present_wrappers")] = (frozenset,)
FIELD_TYPES[("widget", "zorder")] = (tuple,)
FIELD_TYPES[("connection", "hints")] = (tuple, OpaqueElement)
FIELD_TYPES[("customwidget", "header")] = (HeaderDecl, OpaqueElement)
FIELD_TYPES[("customwidget", "sizehint")] = (SizeValue, OpaqueElement)
FIELD_TYPES[("customwidget", "container")] = (int, OpaqueElement)
FIELD_TYPES[("customwidget", "slots")] = (SlotsDecl, OpaqueElement)
FIELD_TYPES[("customwidget", "propertyspecifications")] = (OpaqueElement,)
FIELD_TYPES[("opaque", "element")] = (OpaqueElement,)
FIELD_TYPES[("opaque", "anchor")] = (tuple,)

_MEMBERS: Dict[Tuple[str, str], Tuple[type, ...]] = {
    ("ui", "tabstops"): (str,),
    ("ui", "present_wrappers"): (str,),
    ("widget", "zorder"): (str,),
    ("connection", "hints"): (ConnectionHint,),
}


def field_accepts(kind: str, name: str, value: object) -> bool:
    """True when ``value`` is a declared type for ``kind.name`` (invariant 6)."""
    if (kind, name) == ("opaque", "anchor"):
        return (
            isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
            and not isinstance(value[1], bool)
        )
    expected = FIELD_TYPES.get((kind, name))
    if expected is None or not _matches(value, expected):
        return False
    members = _MEMBERS.get((kind, name))
    if members is None or not isinstance(value, (tuple, frozenset, set)):
        return True
    return all(_matches(item, members) for item in value)


def _matches(value: object, expected: Tuple[type, ...]) -> bool:
    for candidate in expected:
        if candidate is int:
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif isinstance(value, candidate):
            return True
    return False
