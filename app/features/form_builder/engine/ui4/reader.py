"""``.ui`` reader (CONTRACTS.md section 8.1).

Parses with ``xml.parsers.expat`` directly (positions for every element, no
ElementTree tree), refuses DOCTYPE and entity declarations, and builds a
``UiDocument`` through ``engine.ui4.mutate``. Never raises anything but
``UiReadError`` for bad input (fuzz contract, section 13).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.parsers import expat

from app.features.form_builder.engine.diagnostic_codes import fb0xx as _fb0xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID, IdAllocator, NodeId
from app.features.form_builder.engine.ui4 import mutate as mutate_module
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.numfmt import parse_real, real_round_trips
from app.features.form_builder.engine.ui4.opaque import OpaqueComment, OpaqueElement, OpaquePI
from app.features.form_builder.engine.ui4.schema import (
    SCHEMA,
    ConnectionHint,
    HeaderDecl,
    LayoutDefault,
    LayoutFunction,
    SlotsDecl,
)
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    VALUE_CLASSES,
    BoolValue,
    CStringValue,
    CharValue,
    ColorValue,
    CursorShapeValue,
    CursorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    OpaqueValue,
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    SetValue,
    SizeFValue,
    SizePolicyValue,
    SizeValue,
    StringListValue,
    StringValue,
    TimeValue,
    UIntValue,
    ULongLongValue,
    UrlValue,
    Value,
)

# Import registers FB001-FB008.
_ = _fb0xx

#: Inputs larger than this are refused with FB008 (protects the 30 MB budget).
MAX_INPUT_BYTES = 16 * 1024 * 1024
#: Element nesting deeper than this is refused with FB008.
MAX_DEPTH = 256

_INT32 = (-2147483648, 2147483647)
_UINT32 = (0, 4294967295)
_INT64 = (-9223372036854775808, 9223372036854775807)
_UINT64 = (0, 18446744073709551615)
_INT_RE = re.compile(r"[+-]?[0-9]+\Z")
_DEFERRED_VALUES = frozenset({"palette", "brush", "iconset", "pixmap", "gradient"})
_POLICY_BY_INT = {
    "0": "Fixed",
    "1": "Minimum",
    "2": "Maximum",
    "3": "Preferred",
    "4": "MinimumExpanding",
    "5": "Expanding",
    "7": "Ignored",
}
_FONT_INT = frozenset({"pointsize", "weight"})
_FONT_BOOL = frozenset({"italic", "bold", "underline", "strikeout", "antialiasing", "kerning"})
_FONT_TEXT = frozenset({"family", "stylestrategy", "hintingpreference", "fontweight"})


class UiReadError(ValueError):
    """Fatal: the text cannot become a document. The visual editor does not open;
    the tab shows View XML with the text unchanged and a banner.

    ``code``: FB001 malformed XML, FB002 not a ``<ui>`` document or no root
    widget, FB004 DOCTYPE or entity declaration, FB008 too large or too deep.
    ``line``/``column``: 1-based, from expat; 0 when unknown.
    """

    def __init__(self, code: str, message: str, line: int = 0, column: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.line = line
        self.column = column


@dataclass(frozen=True)
class ReadResult:
    """``diagnostics``: non-fatal findings from reading (FB003 newer ui version,
    FB005 value kept as written, FB006 unknown element preserved, FB007
    duplicate property moved to opaque, FB402 newer logic version).
    ``line_map``: node id -> 1-based source line of its start tag."""

    document: UiDocument
    diagnostics: Tuple[FormDiagnostic, ...]
    line_map: Dict[NodeId, int]


@dataclass
class _XNode:
    tag: str
    attrs: Tuple[Tuple[str, str], ...]
    children: Tuple[object, ...]
    line: int


@dataclass
class _Note:
    code: str
    message: str
    line: int
    prop: Optional[str] = None


@dataclass
class _Built:
    kind: str
    line: int
    fields: List[Tuple[str, object]] = field(default_factory=list)
    properties: List[PropertyEntry] = field(default_factory=list)
    attributes: List[PropertyEntry] = field(default_factory=list)
    slots: Dict[str, List["_Built"]] = field(default_factory=dict)
    extra_attrs: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[_Note] = field(default_factory=list)

    def add_slot(self, name: str, child: "_Built") -> None:
        self.slots.setdefault(name, []).append(child)

    def field_map(self) -> Dict[str, object]:
        return dict(self.fields)

    def set_field(self, name: str, value: object) -> None:
        self.fields = [(key, item) for key, item in self.fields if key != name]
        self.fields.append((name, value))


def read_ui(text: str, *, allocator: IdAllocator, source_path: Optional[str] = None) -> ReadResult:
    """Parse ``text`` (a leading BOM is ignored; CRLF and CR are accepted).

    Rules:
    * Whitespace-only text between elements is ignored. Text inside value leaf
      elements (``string``, ``cstring``, ``enum``, ``set``...) is kept exactly.
    * Known elements become typed nodes; unknown child elements become
      OpaqueNodes at ``(group, n)`` (after the n-th typed entry of the
      write-order group they sit in or follow). Unknown attributes are kept
      in input order.
    * A value element that does not parse losslessly becomes OpaqueValue.
    * Ids come from ``allocator`` in pre-order.
    O(input). Budget: 25 ms CPU for a 300-widget form (section 12).
    """
    del source_path
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        encoded = text.encode("utf-8")
    except UnicodeError as exc:
        raise UiReadError("FB001", "This form is not valid XML.", 0, 0) from exc
    if len(encoded) > MAX_INPUT_BYTES:
        raise UiReadError("FB008", "This form is too large to open in the form builder.", 0, 0)
    try:
        root = _parse_tree(text)
        built = _lower_ui(root)
        line_map: Dict[NodeId, int] = {}
        diagnostics: List[FormDiagnostic] = []
        spec = _to_spec(built, allocator, line_map, diagnostics)
        document = mutate_module.load_spec(spec)
    except UiReadError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        raise UiReadError(
            "FB001",
            "This form is not valid XML (%s)." % (type(exc).__name__,),
            0,
            0,
        ) from exc
    return ReadResult(document=document, diagnostics=tuple(diagnostics), line_map=line_map)


def read_fragment(text: str, *, source_path: Optional[str] = None) -> Fragment:
    """Parse clipboard text into a ``Fragment`` with ``id=None``
    everywhere. Accepts a full ``<ui>`` document (its root's children become the
    fragment) or the CBCS fragment MIME payload. Raises UiReadError."""
    result = read_ui(text, allocator=IdAllocator(), source_path=source_path)
    document = result.document
    nodes: List[NodeSpec] = []
    for slot in SCHEMA["widget"].slots:
        if slot.name == "opaque":
            continue
        for child in document.root.children(slot.name):
            nodes.append(_strip_ids(child.to_spec()))
    return Fragment(
        nodes=tuple(nodes),
        connections=tuple(_strip_ids(node.to_spec()) for node in document.connections()),
        customwidgets=tuple(_strip_ids(node.to_spec()) for node in document.ui.children("customwidgets")),
        resources=tuple(_strip_ids(node.to_spec()) for node in document.ui.children("resources")),
    )


def _parse_tree(text: str) -> _XNode:
    parser = expat.ParserCreate()
    parser.ordered_attributes = True
    parser.buffer_text = True
    stack: List[List[object]] = []
    root: List[Optional[_XNode]] = [None]

    def _position() -> Tuple[int, int]:
        return parser.CurrentLineNumber, parser.CurrentColumnNumber + 1

    def start(name: str, attrs: List[str]) -> None:
        if len(stack) >= MAX_DEPTH:
            line, column = _position()
            raise UiReadError("FB008", "This form is nested too deeply to open in the form builder.", line, column)
        pairs = tuple((attrs[index], attrs[index + 1]) for index in range(0, len(attrs), 2))
        stack.append([name, pairs, parser.CurrentLineNumber, []])

    def end(name: str) -> None:
        del name
        frame = stack.pop()
        tag, attrs, line, parts = frame
        node = _XNode(tag=str(tag), attrs=attrs, children=_coalesce(parts), line=int(line))
        if stack:
            stack[-1][3].append(node)
        else:
            root[0] = node

    def data(value: str) -> None:
        if stack:
            stack[-1][3].append(value)

    def comment(value: str) -> None:
        if stack:
            stack[-1][3].append(OpaqueComment(value))

    def pi(target: str, data_text: str) -> None:
        if stack:
            stack[-1][3].append(OpaquePI(target, data_text))

    def doctype(*_args: object) -> None:
        line, column = _position()
        raise UiReadError("FB004", "This form uses a DOCTYPE, which the form builder refuses.", line, column)

    def entity(*_args: object) -> None:
        line, column = _position()
        raise UiReadError("FB004", "This form declares an XML entity, which the form builder refuses.", line, column)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    parser.CommentHandler = comment
    parser.ProcessingInstructionHandler = pi
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    try:
        parser.Parse(text, True)
    except UiReadError:
        raise
    except expat.ExpatError as exc:
        raise UiReadError(
            "FB001",
            "This form is not valid XML.",
            parser.ErrorLineNumber or 0,
            (parser.ErrorColumnNumber or 0) + 1,
        ) from exc
    if root[0] is None:
        raise UiReadError("FB002", "This file is not a form.", 0, 0)
    return root[0]


def _coalesce(parts: List[object]) -> Tuple[object, ...]:
    merged: List[object] = []
    for part in parts:
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] = merged[-1] + part
        else:
            merged.append(part)
    return tuple(merged)


class _Cursor:
    """Write-order position: ``(group, n)`` after ``n`` typed entries of ``group``."""

    def __init__(self) -> None:
        self.anchor: Tuple[str, int] = ("", 0)

    def here(self) -> Tuple[str, int]:
        return self.anchor

    def advance(self, group: str) -> None:
        if self.anchor[0] == group:
            self.anchor = (group, self.anchor[1] + 1)
        else:
            self.anchor = (group, 1)

    def enter(self, group: str, count: int) -> None:
        self.anchor = (group, count)


def _lower_ui(node: _XNode) -> _Built:
    if node.tag != "ui":
        raise UiReadError("FB002", "This file is not a form.", node.line, 0)
    built = _Built(kind="ui", line=node.line)
    fields, extra = _split_attrs("ui", node.attrs)
    built.fields = fields
    built.extra_attrs = extra
    version = built.field_map().get("version")
    if not (isinstance(version, str) and version.split(".")[0] == "4"):
        shown = version if isinstance(version, str) else ""
        built.notes.append(_Note("FB003", 'This form says version "%s". The form builder expects 4.x.' % shown, node.line))
    cursor = _Cursor()
    wrappers: set = set()
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                built.add_slot("opaque", _text_opaque(child, cursor.here(), node.line))
            continue
        if isinstance(child, (OpaqueComment, OpaquePI)):
            continue
        if not isinstance(child, _XNode):
            continue
        group = _ui_group(child.tag)
        if group is None:
            built.add_slot("opaque", _opaque_built(child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
            continue
        _place_ui_child(built, child, wrappers, cursor, group)
    if "root" not in built.slots:
        raise UiReadError("FB002", "This form has no root widget.", node.line, 0)
    built.set_field("present_wrappers", frozenset(wrappers))
    _order_fields(built)
    return built


def _ui_group(tag: str) -> Optional[str]:
    return {
        "author": "child:author",
        "comment": "child:comment",
        "exportmacro": "child:exportmacro",
        "class": "child:class",
        "widget": "root",
        "layoutdefault": "child:layoutdefault",
        "layoutfunction": "child:layoutfunction",
        "pixmapfunction": "child:pixmapfunction",
        "customwidgets": "customwidgets",
        "tabstops": "child:tabstops",
        "images": "child:images",
        "includes": "includes",
        "resources": "resources",
        "connections": "connections",
        "designerdata": "child:designerdata",
        "slots": "child:slots",
        "buttongroups": "buttongroups",
    }.get(tag)


def _place_ui_child(
    built: _Built,
    child: _XNode,
    wrappers: set,
    cursor: _Cursor,
    group: str,
) -> None:
    tag = child.tag
    if tag in ("author", "comment", "exportmacro", "pixmapfunction"):
        built.set_field(tag if tag != "pixmapfunction" else "pixmapfunction", _exact_text(child))
        cursor.advance(group)
        return
    if tag == "class":
        built.set_field("class_name", _exact_text(child))
        cursor.advance(group)
        return
    if tag == "widget":
        if "root" in built.slots:
            built.add_slot("opaque", _opaque_built(child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept an extra root widget.", child.line))
            return
        built.add_slot("root", _lower_widget(child))
        cursor.advance("root")
        return
    if tag == "layoutdefault":
        built.set_field("layoutdefault", _layout_default(child))
        cursor.advance(group)
        return
    if tag == "layoutfunction":
        built.set_field("layoutfunction", _layout_function(child))
        cursor.advance(group)
        return
    if tag == "tabstops":
        names = tuple(_exact_text(item) for item in _elements(child) if item.tag == "tabstop")
        built.set_field("tabstops", names)
        cursor.advance(group)
        return
    if tag == "images":
        built.set_field("images", _to_opaque(child))
        cursor.advance(group)
        return
    if tag == "designerdata":
        built.set_field("designerdata", _to_opaque(child))
        cursor.advance(group)
        return
    if tag == "slots":
        built.set_field("form_slots", _slots_decl(child))
        cursor.advance(group)
        return
    if tag in ("customwidgets", "includes", "resources", "connections", "buttongroups"):
        count = _lower_wrapper(built, child, tag, wrappers)
        cursor.enter(group, count)
        return


def _lower_wrapper(built: _Built, node: _XNode, tag: str, wrappers: set) -> int:
    slot = {
        "customwidgets": "customwidgets",
        "includes": "includes",
        "resources": "resources",
        "connections": "connections",
        "buttongroups": "buttongroups",
    }[tag]
    if node.attrs:
        wrappers.discard(tag)
        built.add_slot("opaque", _opaque_built(node, (slot, 0)))
        built.notes.append(_Note("FB006", "Kept attributes on <%s>." % tag, node.line))
        return 0
    wrappers.add(tag)
    typed = 0
    for child in _elements(node):
        lowered = _lower_known(child, tag)
        if lowered is None:
            built.add_slot("opaque", _opaque_built(child, (slot, typed)))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
        else:
            built.add_slot(slot, lowered)
            typed += 1
    return typed


def _lower_known(node: _XNode, parent_tag: str) -> Optional[_Built]:
    if parent_tag == "customwidgets" and node.tag == "customwidget":
        return _lower_custom(node)
    if parent_tag == "includes" and node.tag == "include":
        return _lower_include(node)
    if parent_tag == "resources" and node.tag == "include":
        return _lower_resource(node)
    if parent_tag == "connections" and node.tag == "connection":
        return _lower_connection(node)
    if parent_tag == "buttongroups" and node.tag == "buttongroup":
        return _lower_named_box(node, "buttongroup")
    return None


def _lower_widget(node: _XNode) -> _Built:
    return _lower_box(node, "widget")


def _lower_box(node: _XNode, kind: str) -> _Built:
    built = _Built(kind=kind, line=node.line)
    fields, extra = _split_attrs(kind, node.attrs)
    built.fields = fields
    built.extra_attrs = extra
    _ensure_required(built)
    cursor = _Cursor()
    properties: List[Tuple[PropertyEntry, _XNode, List[_Note]]] = []
    attributes: List[Tuple[PropertyEntry, _XNode, List[_Note]]] = []
    prop_stream: List[Tuple[str, object]] = []
    attr_stream: List[Tuple[str, object]] = []
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                _hold_gap(built, cursor, prop_stream, attr_stream, ("gap-text", (child, node.line)))
            continue
        if not isinstance(child, _XNode):
            continue
        group = _box_group(kind, child.tag, built)
        if group == "layout" and "layout" in built.slots:
            built.add_slot("opaque", _opaque_built(child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept an extra layout.", child.line))
            continue
        if group == "properties":
            entry, notes = _parse_property(child, "property")
            properties.append((entry, child, notes))
            prop_stream.append(("entry", len(properties) - 1))
            cursor.enter("properties", 0)
            continue
        if group == "attributes":
            entry, notes = _parse_property(child, "attribute")
            attributes.append((entry, child, notes))
            attr_stream.append(("entry", len(attributes) - 1))
            cursor.enter("attributes", 0)
            continue
        if group is None:
            _hold_gap(built, cursor, prop_stream, attr_stream, ("gap-node", child))
            continue
        _place_box_child(built, child, group)
        cursor.advance(group)
    _realize_entries(built, properties, prop_stream, "properties")
    _realize_entries(built, attributes, attr_stream, "attributes")
    if kind == "header" and not built.field_map().get("axis"):
        built.set_field("axis", "row")
    _order_fields(built)
    return built


def _box_group(kind: str, tag: str, built: _Built) -> Optional[str]:
    spec = SCHEMA[kind]
    if tag == "property" and spec.has_properties:
        return "properties"
    if tag == "attribute" and spec.has_attributes:
        return "attributes"
    if kind == "widget":
        return {
            "row": "rows",
            "column": "columns",
            "item": "items",
            "layout": "layout",
            "widget": "children",
            "action": "actions",
            "actiongroup": "action_groups",
            "addaction": "add_actions",
            "zorder": "child:zorder",
        }.get(tag)
    if kind == "layout" and tag == "item":
        return "layout_items"
    if kind == "layoutitem" and tag in ("widget", "layout", "spacer"):
        if built.slots.get("content"):
            return None
        return "content"
    if kind == "item" and tag == "item":
        return "subitems"
    if kind == "actiongroup" and tag == "action":
        return "actions"
    if kind == "actiongroup" and tag == "actiongroup":
        return "action_groups"
    return None


def _place_box_child(built: _Built, child: _XNode, group: str) -> None:
    if group == "child:zorder":
        current = built.field_map().get("zorder")
        names = list(current) if isinstance(current, tuple) else []
        names.append(_exact_text(child))
        built.set_field("zorder", tuple(names))
        return
    if group == "rows":
        header = _lower_box(child, "header")
        header.set_field("axis", "row")
        built.add_slot("rows", header)
        return
    if group == "columns":
        header = _lower_box(child, "header")
        header.set_field("axis", "column")
        built.add_slot("columns", header)
        return
    if group == "items":
        built.add_slot("items", _lower_box(child, "item"))
        return
    if group == "subitems":
        built.add_slot("subitems", _lower_box(child, "item"))
        return
    if group == "layout":
        built.add_slot("layout", _lower_box(child, "layout"))
        return
    if group == "layout_items":
        built.add_slot("layout_items", _lower_box(child, "layoutitem"))
        return
    if group == "content":
        if child.tag == "widget":
            built.add_slot("content", _lower_box(child, "widget"))
        elif child.tag == "layout":
            built.add_slot("content", _lower_box(child, "layout"))
        elif child.tag == "spacer":
            built.add_slot("content", _lower_box(child, "spacer"))
        return
    if group == "children":
        built.add_slot("children", _lower_box(child, "widget"))
        return
    if group == "actions":
        built.add_slot("actions", _lower_box(child, "action"))
        return
    if group == "action_groups":
        built.add_slot("action_groups", _lower_box(child, "actiongroup"))
        return
    if group == "add_actions":
        built.add_slot("add_actions", _lower_box(child, "actionref"))


def _lower_custom(node: _XNode) -> _Built:
    built = _Built(kind="customwidget", line=node.line)
    cursor = _Cursor()
    for child in _elements(node):
        tag = child.tag
        if tag == "class":
            built.set_field("class_name", _exact_text(child))
            cursor.advance("child:class")
        elif tag == "extends":
            built.set_field("extends", _exact_text(child))
            cursor.advance("child:extends")
        elif tag == "header":
            location = dict(child.attrs).get("location")
            built.set_field("header", HeaderDecl(_exact_text(child), location))
            cursor.advance("child:header")
        elif tag == "sizehint":
            width = _child_int(child, "width")
            height = _child_int(child, "height")
            if width is None or height is None:
                built.add_slot("opaque", _opaque_built(child, cursor.here()))
            else:
                built.set_field("sizehint", SizeValue(width, height))
                cursor.advance("child:sizehint")
        elif tag == "addpagemethod":
            built.set_field("addpagemethod", _exact_text(child))
            cursor.advance("child:addpagemethod")
        elif tag == "container":
            number = _parse_int(_exact_text(child), _INT32)
            if number is None:
                built.add_slot("opaque", _opaque_built(child, cursor.here()))
            else:
                built.set_field("container", number)
                cursor.advance("child:container")
        elif tag == "pixmap":
            built.set_field("pixmap", _exact_text(child))
            cursor.advance("child:pixmap")
        elif tag == "slots":
            built.set_field("slots", _slots_decl(child))
            cursor.advance("child:slots")
        elif tag == "propertyspecifications":
            built.set_field("propertyspecifications", _to_opaque(child))
            cursor.advance("child:propertyspecifications")
        else:
            built.add_slot("opaque", _opaque_built(child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % tag, child.line))
    if "class_name" not in built.field_map():
        built.set_field("class_name", "")
    if "extends" not in built.field_map():
        built.set_field("extends", "")
    _order_fields(built)
    return built


def _lower_include(node: _XNode) -> _Built:
    built = _Built(kind="include", line=node.line)
    fields, extra = _split_attrs("include", node.attrs)
    built.fields = fields
    built.extra_attrs = extra
    text = _exact_text(node)
    if text:
        built.set_field("text", text)
    _order_fields(built)
    return built


def _lower_resource(node: _XNode) -> _Built:
    built = _Built(kind="resource", line=node.line)
    fields, extra = _split_attrs("resource", node.attrs)
    built.fields = fields
    built.extra_attrs = extra
    if "location" not in built.field_map():
        built.set_field("location", "")
    _order_fields(built)
    return built


def _lower_connection(node: _XNode) -> _Built:
    built = _Built(kind="connection", line=node.line)
    cursor = _Cursor()
    for child in _elements(node):
        if child.tag in ("sender", "signal", "receiver", "slot"):
            built.set_field(child.tag, _exact_text(child))
            cursor.advance("child:" + child.tag)
        elif child.tag == "hints":
            hints = []
            for hint in _elements(child):
                if hint.tag != "hint":
                    continue
                hint_type = dict(hint.attrs).get("type", "")
                x_value = _child_int(hint, "x")
                y_value = _child_int(hint, "y")
                hints.append(ConnectionHint(hint_type, 0 if x_value is None else x_value, 0 if y_value is None else y_value))
            built.set_field("hints", tuple(hints))
            cursor.advance("child:hints")
        else:
            built.add_slot("opaque", _opaque_built(child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
    for name in ("sender", "signal", "receiver", "slot"):
        if name not in built.field_map():
            built.set_field(name, "")
    _order_fields(built)
    return built


def _lower_named_box(node: _XNode, kind: str) -> _Built:
    return _lower_box(node, kind)


def _parse_property(node: _XNode, kind: str) -> Tuple[PropertyEntry, List[_Note]]:
    attrs = list(node.attrs)
    name = ""
    stdset = None
    extra: List[Tuple[str, str]] = []
    for key, value in attrs:
        if key == "name" and name == "":
            name = value
        elif key == "stdset" and stdset is None:
            stdset = value
        else:
            extra.append((key, value))
    notes: List[_Note] = []
    elements = _elements(node)
    if len(elements) != 1 or _has_significant_text(node) or _has_comment(node):
        value: Value = OpaqueValue(_to_opaque(_synthetic_value(node)))
        notes.append(_Note("FB005", "Kept this property value as written.", node.line, name or None))
    else:
        parsed = _parse_value(elements[0])
        if parsed is None:
            value = OpaqueValue(_to_opaque(elements[0]))
            notes.append(_Note("FB005", "Kept this <%s> value as written." % elements[0].tag, elements[0].line, name or None))
        else:
            value = parsed
    return PropertyEntry(kind=kind, name=name, value=value, stdset=stdset, extra_attrs=tuple(extra)), notes


def _hold_gap(
    built: _Built,
    cursor: _Cursor,
    prop_stream: List[Tuple[str, object]],
    attr_stream: List[Tuple[str, object]],
    item: Tuple[str, object],
) -> None:
    group = cursor.anchor[0]
    if group == "properties":
        prop_stream.append(item)
        return
    if group == "attributes":
        attr_stream.append(item)
        return
    kind, payload = item
    if kind == "gap-text" and isinstance(payload, tuple) and len(payload) == 2:
        text, line = payload
        if isinstance(text, str) and isinstance(line, int):
            built.add_slot("opaque", _text_opaque(text, cursor.here(), line))
        return
    if isinstance(payload, _XNode):
        built.add_slot("opaque", _opaque_built(payload, cursor.here()))
        built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % payload.tag, payload.line))


def _realize_entries(
    built: _Built,
    entries: List[Tuple[PropertyEntry, _XNode, List[_Note]]],
    stream: List[Tuple[str, object]],
    group: str,
) -> None:
    """Last copy of each name is typed. Earlier copies and gaps keep input order.

    ``n`` counts surviving typed entries before the opaque, so an earlier
    duplicate stays earlier than the winner (CONTRACTS.md section 2.3).
    """
    last_index: Dict[str, int] = {}
    for index, (entry, _source, _notes) in enumerate(entries):
        last_index[entry.name] = index
    typed: List[PropertyEntry] = []
    typed_so_far = 0
    for kind, payload in stream:
        if kind == "entry":
            if not isinstance(payload, int):
                continue
            entry, source, notes = entries[payload]
            if last_index[entry.name] != payload:
                built.add_slot("opaque", _opaque_built(source, (group, typed_so_far)))
                built.notes.append(
                    _Note(
                        "FB007",
                        'Property "%s" is set more than once. The last value is the one that is used.' % entry.name,
                        source.line,
                        entry.name,
                    )
                )
                continue
            typed.append(entry)
            built.notes.extend(notes)
            typed_so_far += 1
            continue
        if kind == "gap-text" and isinstance(payload, tuple) and len(payload) == 2:
            text, line = payload
            if isinstance(text, str) and isinstance(line, int):
                built.add_slot("opaque", _text_opaque(text, (group, typed_so_far), line))
            continue
        if kind == "gap-node" and isinstance(payload, _XNode):
            built.add_slot("opaque", _opaque_built(payload, (group, typed_so_far)))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % payload.tag, payload.line))
    if group == "properties":
        built.properties = typed
    else:
        built.attributes = typed


def _parse_value(node: _XNode) -> Optional[Value]:
    tag = node.tag
    if tag in _DEFERRED_VALUES or tag not in VALUE_CLASSES:
        return None
    if tag == "bool":
        text = _exact_text(node).strip()
        if text == "true":
            return BoolValue(True)
        if text == "false":
            return BoolValue(False)
        return None
    if tag in ("number", "uint", "longlong", "ulonglong", "cursor"):
        limits = {"number": _INT32, "uint": _UINT32, "longlong": _INT64, "ulonglong": _UINT64, "cursor": _INT32}[tag]
        number = _parse_int(_exact_text(node), limits)
        if number is None:
            return None
        cls = VALUE_CLASSES[tag]
        return cls(number)  # type: ignore[call-arg, no-any-return]
    if tag in ("double", "float"):
        value = _lossless_real(_exact_text(node), tag)
        if value is None:
            return None
        if tag == "double":
            return DoubleValue(value)
        return FloatValue(value)
    if tag == "string":
        return _parse_string(node)
    if tag == "cstring":
        if node.attrs or not _is_plain(node):
            return None
        return CStringValue(_exact_text(node))
    if tag in ("enum", "set", "cursorshape"):
        if node.attrs or not _is_plain(node):
            return None
        text = _exact_text(node)
        if tag == "enum":
            return EnumValue(text)
        if tag == "set":
            return SetValue(text)
        return CursorShapeValue(text)
    if tag == "stringlist":
        return _parse_stringlist(node)
    if tag == "rect":
        return _int_record(node, RectValue, ("x", "y", "width", "height"))
    if tag == "rectf":
        return _real_record(node, RectFValue, ("x", "y", "width", "height"))
    if tag == "size":
        return _int_record(node, SizeValue, ("width", "height"))
    if tag == "sizef":
        return _real_record(node, SizeFValue, ("width", "height"))
    if tag == "point":
        return _int_record(node, PointValue, ("x", "y"))
    if tag == "pointf":
        return _real_record(node, PointFValue, ("x", "y"))
    if tag == "sizepolicy":
        return _parse_sizepolicy(node)
    if tag == "font":
        return _parse_font(node)
    if tag == "char":
        if _has_noise(node):
            return None
        number = _child_int(node, "unicode")
        if number is None:
            return None
        return CharValue(number)
    if tag == "color":
        return _parse_color(node)
    if tag == "date":
        return _int_record(node, DateValue, ("year", "month", "day"))
    if tag == "time":
        return _int_record(node, TimeValue, ("hour", "minute", "second"))
    if tag == "datetime":
        return _int_record(node, DateTimeValue, ("hour", "minute", "second", "year", "month", "day"))
    if tag == "locale":
        attrs = dict(node.attrs)
        if "language" not in attrs or "country" not in attrs or _elements(node):
            return None
        return LocaleValue(attrs["language"], attrs["country"])
    if tag == "url":
        strings = [child for child in _elements(node) if child.tag == "string"]
        if len(strings) != 1:
            return None
        parsed = _parse_string(strings[0])
        if parsed is None:
            return None
        return UrlValue(parsed)
    return None


def _parse_string(node: _XNode) -> Optional[StringValue]:
    if not _is_plain(node):
        return None
    notr = None
    comment = None
    extracomment = None
    string_id = None
    for key, value in node.attrs:
        if key == "notr" and notr is None and value in ("true", "false"):
            notr = value == "true"
        elif key == "comment" and comment is None:
            comment = value
        elif key == "extracomment" and extracomment is None:
            extracomment = value
        elif key == "id" and string_id is None:
            string_id = value
        else:
            return None
    return StringValue(_exact_text(node), notr, comment, extracomment, string_id)


def _parse_stringlist(node: _XNode) -> Optional[StringListValue]:
    holder = _parse_string(_XNode(node.tag, node.attrs, tuple(child for child in node.children if isinstance(child, str)), node.line))
    if holder is None and node.attrs:
        return None
    items = []
    for child in _elements(node):
        if child.tag != "string" or child.attrs or not _is_plain(child):
            return None
        items.append(_exact_text(child))
    if holder is None:
        return StringListValue(tuple(items))
    return StringListValue(tuple(items), holder.notr, holder.comment, holder.extracomment, holder.id)


def _parse_sizepolicy(node: _XNode) -> Optional[SizePolicyValue]:
    if _has_noise(node):
        return None
    attrs = dict(node.attrs)
    horizontal = attrs.get("hsizetype")
    vertical = attrs.get("vsizetype")
    horstretch = 0
    verstretch = 0
    for child in _elements(node):
        text = _exact_text(child).strip()
        if child.tag == "hsizetype" and horizontal is None:
            horizontal = _POLICY_BY_INT.get(text, text if not text.isdigit() else None)
        elif child.tag == "vsizetype" and vertical is None:
            vertical = _POLICY_BY_INT.get(text, text if not text.isdigit() else None)
        elif child.tag == "horstretch":
            number = _parse_int(text, _INT32)
            if number is None:
                return None
            horstretch = number
        elif child.tag == "verstretch":
            number = _parse_int(text, _INT32)
            if number is None:
                return None
            verstretch = number
        else:
            return None
    if not horizontal or not vertical:
        return None
    return SizePolicyValue(horizontal, vertical, horstretch, verstretch)


def _parse_font(node: _XNode) -> Optional[FontValue]:
    if _has_noise(node):
        return None
    values: Dict[str, object] = {}
    for child in _elements(node):
        if child.tag in values or child.tag not in _FONT_INT | _FONT_BOOL | _FONT_TEXT:
            return None
        if child.tag in _FONT_INT:
            number = _parse_int(_exact_text(child), _INT32)
            if number is None:
                return None
            values[child.tag] = number
        elif child.tag in _FONT_BOOL:
            text = _exact_text(child).strip()
            if text not in ("true", "false"):
                return None
            values[child.tag] = text == "true"
        else:
            text = _exact_text(child)
            if not _is_plain(child):
                nested = [item for item in _elements(child) if item.tag == "string"]
                if len(nested) == 1 and _is_plain(nested[0]):
                    text = _exact_text(nested[0])
                else:
                    return None
            values[child.tag] = text
    return FontValue(**values)  # type: ignore[arg-type]


def _parse_color(node: _XNode) -> Optional[ColorValue]:
    if _has_noise(node):
        return None
    red = _child_int(node, "red")
    green = _child_int(node, "green")
    blue = _child_int(node, "blue")
    if red is None or green is None or blue is None:
        return None
    alpha = None
    raw_alpha = dict(node.attrs).get("alpha")
    if raw_alpha is not None:
        alpha = _parse_int(raw_alpha, _INT32)
        if alpha is None:
            return None
    return ColorValue(red, green, blue, alpha)


def _int_record(node: _XNode, cls: type, names: Tuple[str, ...]) -> Optional[Value]:
    if _has_noise(node):
        return None
    found: Dict[str, int] = {}
    for child in _elements(node):
        if child.tag in found or child.tag not in names:
            return None
        number = _parse_int(_exact_text(child), _INT32)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != set(names):
        return None
    return cls(*(found[name] for name in names))  # type: ignore[no-any-return, operator]


def _real_record(node: _XNode, cls: type, names: Tuple[str, ...]) -> Optional[Value]:
    if _has_noise(node):
        return None
    found: Dict[str, float] = {}
    for child in _elements(node):
        if child.tag in found or child.tag not in names:
            return None
        number = _lossless_real(_exact_text(child))
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != set(names):
        return None
    return cls(*(found[name] for name in names))  # type: ignore[no-any-return, operator]


def _layout_default(node: _XNode) -> LayoutDefault:
    attrs = dict(node.attrs)
    return LayoutDefault(_parse_int(attrs["spacing"], _INT32) if "spacing" in attrs else None, _parse_int(attrs["margin"], _INT32) if "margin" in attrs else None)


def _layout_function(node: _XNode) -> LayoutFunction:
    attrs = dict(node.attrs)
    return LayoutFunction(attrs.get("spacing"), attrs.get("margin"))


def _slots_decl(node: _XNode) -> SlotsDecl:
    signals = tuple(_exact_text(child) for child in _elements(node) if child.tag == "signal")
    slots = tuple(_exact_text(child) for child in _elements(node) if child.tag == "slot")
    return SlotsDecl(signals, slots)


def _split_attrs(kind: str, attrs: Tuple[Tuple[str, str], ...]) -> Tuple[List[Tuple[str, object]], List[Tuple[str, str]]]:
    known = {field.xml[len("attr:"):]: field.name for field in SCHEMA[kind].fields if field.xml.startswith("attr:")}
    int_fields = {"row", "column", "rowspan", "colspan"}
    fields: List[Tuple[str, object]] = []
    extra: List[Tuple[str, str]] = []
    for key, value in attrs:
        field_name = known.get(key)
        if field_name is None:
            extra.append((key, value))
            continue
        if field_name in int_fields:
            number = _parse_int(value, _INT32)
            if number is None:
                extra.append((key, value))
            else:
                fields.append((field_name, number))
            continue
        fields.append((field_name, value))
    return fields, extra


def _ensure_required(built: _Built) -> None:
    mapping = built.field_map()
    for item in SCHEMA[built.kind].fields:
        if item.required and item.name not in mapping:
            built.set_field(item.name, "")


def _order_fields(built: _Built) -> None:
    order = [item.name for item in SCHEMA[built.kind].fields]
    built.fields.sort(key=lambda item: order.index(item[0]) if item[0] in order else 1000)


def _to_spec(
    built: _Built,
    allocator: IdAllocator,
    line_map: Dict[NodeId, int],
    diagnostics: List[FormDiagnostic],
) -> NodeSpec:
    node_id = DOCUMENT_ID if built.kind == "ui" else allocator.alloc()
    line_map[node_id] = built.line
    object_name = _built_name(built)
    for note in built.notes:
        info = CODES.get(note.code)
        severity = info.severity if info is not None else Severity.INFO
        diagnostics.append(
            FormDiagnostic(
                code=note.code,
                severity=severity,
                message=note.message,
                location=DiagnosticLocation(
                    node_id=node_id,
                    object_name=object_name,
                    property=note.prop,
                    line=note.line,
                ),
                source="reader",
            )
        )
    slots = []
    for slot in SCHEMA[built.kind].slots:
        kids = built.slots.get(slot.name, [])
        if not kids:
            continue
        slots.append((slot.name, tuple(_to_spec(child, allocator, line_map, diagnostics) for child in kids)))
    return NodeSpec(
        kind=built.kind,
        id=node_id,
        fields=tuple(built.fields),
        properties=tuple(built.properties),
        attributes=tuple(built.attributes),
        slots=tuple(slots),
        extra_attrs=tuple(built.extra_attrs),
    )


def _built_name(built: _Built) -> Optional[str]:
    mapping = built.field_map()
    for name in ("object_name", "name", "class_name"):
        value = mapping.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _strip_ids(spec: NodeSpec) -> NodeSpec:
    return NodeSpec(
        kind=spec.kind,
        id=None,
        fields=spec.fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=tuple((name, tuple(_strip_ids(child) for child in kids)) for name, kids in spec.slots),
        extra_attrs=spec.extra_attrs,
    )


def _opaque_built(node: _XNode, anchor: Tuple[str, int]) -> _Built:
    built = _Built(kind="opaque", line=node.line)
    built.set_field("element", _to_opaque(node))
    built.set_field("anchor", anchor)
    return built


def _text_opaque(text: str, anchor: Tuple[str, int], line: int) -> _Built:
    built = _Built(kind="opaque", line=line)
    built.set_field("element", OpaqueElement("", (), (text,)))
    built.set_field("anchor", anchor)
    return built


def _to_opaque(node: _XNode) -> OpaqueElement:
    children: List[object] = []
    for child in node.children:
        if isinstance(child, str):
            children.append(child)
        elif isinstance(child, _XNode):
            children.append(_to_opaque(child))
        elif isinstance(child, (OpaqueComment, OpaquePI)):
            children.append(child)
    return OpaqueElement(node.tag, node.attrs, tuple(children))


def _synthetic_value(node: _XNode) -> _XNode:
    elements = [child for child in node.children if not isinstance(child, str) or child.strip()]
    if len(elements) == 1 and isinstance(elements[0], _XNode):
        return elements[0]
    return _XNode("#value", (), node.children, node.line)


def _elements(node: _XNode) -> List[_XNode]:
    return [child for child in node.children if isinstance(child, _XNode)]


def _exact_text(node: _XNode) -> str:
    return "".join(child for child in node.children if isinstance(child, str))


def _is_plain(node: _XNode) -> bool:
    return all(isinstance(child, str) for child in node.children)


def _has_significant_text(node: _XNode) -> bool:
    return any(isinstance(child, str) and child.strip() for child in node.children)


def _has_comment(node: _XNode) -> bool:
    return any(isinstance(child, (OpaqueComment, OpaquePI)) for child in node.children)


def _has_noise(node: _XNode) -> bool:
    return _has_comment(node) or _has_significant_text(node)


def _child_text(node: _XNode, tag: str) -> Optional[str]:
    found = [child for child in _elements(node) if child.tag == tag]
    if len(found) != 1:
        return None
    return _exact_text(found[0])


def _child_int(node: _XNode, tag: str) -> Optional[int]:
    text = _child_text(node, tag)
    if text is None:
        return None
    return _parse_int(text, _INT32)


def _parse_int(text: str, limits: Tuple[int, int]) -> Optional[int]:
    stripped = text.strip()
    if _INT_RE.match(stripped) is None:
        return None
    try:
        value = int(stripped, 10)
    except ValueError:
        return None
    if value < limits[0] or value > limits[1]:
        return None
    return value


def _lossless_real(text: str, element: str = "double") -> Optional[float]:
    try:
        value = parse_real(text)
    except ValueError:
        return None
    if not real_round_trips(value, element=element):
        return None
    if value == 0.0 and not _is_zero_literal(text.strip()):
        return None
    return value


def _is_zero_literal(text: str) -> bool:
    body = text[1:] if text[:1] in "+-" else text
    parts = re.split(r"[eE]", body, maxsplit=1)
    digits = parts[0].replace(".", "")
    return bool(digits) and set(digits) <= {"0"}
