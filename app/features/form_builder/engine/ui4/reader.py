"""``.ui`` reader (CONTRACTS.md section 8.1).

Parses with ``xml.parsers.expat`` directly (positions for every element, no
ElementTree tree), refuses DOCTYPE and entity declarations, and builds a
``UiDocument`` through ``engine.ui4.mutate``. Never raises anything but
``UiReadError`` for bad input (fuzz contract, section 13).
"""

from __future__ import annotations

import gc
import re
import threading
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple, TypeVar
from xml.parsers import expat

from app.features.form_builder.engine.diagnostic_codes import fb0xx as _fb0xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID, IdAllocator, NodeId
from app.features.form_builder.engine.query.tree import form_item_role, form_occupied_cells
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
    build_node,
)
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
    BrushValue,
    CStringValue,
    CharValue,
    ColorRole,
    ColorValue,
    CursorShapeValue,
    CursorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    GradientStop,
    GradientValue,
    ICON_STATES,
    IconSetValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    OpaqueValue,
    PaletteValue,
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    ResourcePixmap,
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
# QUiLoader applies each bare <color> to QPalette.ColorRole in value order,
# including NoRole. Checked against PySide 6.8. NColorRoles is not paintable.
_LEGACY_COLOR_ROLES = (
    "WindowText",
    "Button",
    "Light",
    "Midlight",
    "Dark",
    "Mid",
    "Text",
    "BrightText",
    "ButtonText",
    "Base",
    "Window",
    "Shadow",
    "Highlight",
    "HighlightedText",
    "Link",
    "LinkVisited",
    "AlternateBase",
    "NoRole",
    "ToolTipBase",
    "ToolTipText",
    "PlaceholderText",
    "Accent",
)
_PALETTE_GROUPS = ("active", "inactive", "disabled")
# Qt 6.8 writes cursorShape and gradientstop. The schema spellings still occur
# in older files. Qt reads both casings.
_CURSOR_SHAPE_TAGS = frozenset({"cursorshape", "cursorShape"})
# Qt 6.8 writes longLong, UInt and uLongLong. Older files and the schema use
# the lowercase names. Qt reads both casings.
_INT_TAG_ALIASES = {"longLong": "longlong", "UInt": "uint", "uLongLong": "ulonglong"}
_GRADIENT_STOP_TAGS = frozenset({"gradientStop", "gradientstop"})
_GRADIENT_TEXT_ATTRS = frozenset({"type", "spread", "coordinatemode"})
_GRADIENT_REAL_ATTRS = frozenset(
    {
        "startx",
        "starty",
        "endx",
        "endy",
        "centralx",
        "centraly",
        "focalx",
        "focaly",
        "radius",
        "angle",
    }
)
# QSizePolicy::Policy values, not the old SizeType index. 5 is Preferred.
_POLICY_BY_INT = {
    "0": "Fixed",
    "1": "Minimum",
    "3": "MinimumExpanding",
    "4": "Maximum",
    "5": "Preferred",
    "7": "Expanding",
    "13": "Ignored",
}
_FONT_INT = frozenset({"pointsize", "weight"})
_FONT_BOOL = frozenset({"italic", "bold", "underline", "strikeout", "antialiasing", "kerning"})
_FONT_TEXT = frozenset({"family", "stylestrategy", "hintingpreference", "fontweight"})
_INT_LIMITS = {
    "number": _INT32,
    "uint": _UINT32,
    "longlong": _INT64,
    "ulonglong": _UINT64,
    "cursor": _INT32,
}
_INT_ATTR_NAMES = frozenset({"row", "column", "rowspan", "colspan"})
_NO_ATTRS: Tuple[Tuple[str, str], ...] = ()
_NO_CHILDREN: Tuple[object, ...] = ()
_NO_FIELDS: Tuple[Tuple[str, object], ...] = ()
_NO_PROPS: Tuple[PropertyEntry, ...] = ()
_NO_SLOTS: Tuple[Tuple[str, Tuple[Node, ...]], ...] = ()
_NO_NOTES: List["_Note"] = []
_POOL_CAP = 20000
# One read shares identical frozen values and property entries. The cache is
# thread-local so overlapping reads do not see each other's objects, and it
# is cleared when the outermost read returns so it does not pin them.
_INTERN = threading.local()
_WIDGET_CHILD_GROUP = {
    "row": "rows",
    "column": "columns",
    "item": "items",
    "layout": "layout",
    "widget": "children",
    "action": "actions",
    "actiongroup": "action_groups",
    "addaction": "add_actions",
    "zorder": "child:zorder",
}
_UI_CHILD_GROUP = {
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
}
_WRAPPER_SLOT = {
    "customwidgets": "customwidgets",
    "includes": "includes",
    "resources": "resources",
    "connections": "connections",
    "buttongroups": "buttongroups",
}


def _compile_lookups() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, int]], Dict[str, Tuple[str, ...]]]:
    attr: Dict[str, Dict[str, str]] = {}
    rank: Dict[str, Dict[str, int]] = {}
    required: Dict[str, Tuple[str, ...]] = {}
    prefix = "attr:"
    width = len(prefix)
    for kind, spec in SCHEMA.items():
        attr[kind] = {
            item.xml[width:]: item.name
            for item in spec.fields
            if item.xml.startswith(prefix)
        }
        rank[kind] = {item.name: index for index, item in enumerate(spec.fields)}
        required[kind] = tuple(item.name for item in spec.fields if item.required)
    return attr, rank, required


def _field_key(rank: Dict[str, int]):
    return lambda item, rank=rank: rank.get(item[0], 1000)


_ATTR_FIELD, _FIELD_RANK, _REQUIRED_FIELD = _compile_lookups()
_FIELD_KEY = {kind: _field_key(rank) for kind, rank in _FIELD_RANK.items()}


class _Miss:
    """Sentinel: a fast path does not apply; the general parser must run."""


_MISS = _Miss()


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


class _XNode:
    """One element. Children stay a list when expat already coalesced text."""

    __slots__ = ("tag", "attrs", "children", "line")

    def __init__(
        self,
        tag: str,
        attrs: Tuple[Tuple[str, str], ...],
        children: Sequence[object],
        line: int,
    ) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children = children
        self.line = line


@dataclass
class _Note:
    code: str
    message: str
    line: int
    prop: Optional[str] = None


class _Built:
    __slots__ = ("kind", "line", "fields", "properties", "attributes", "slots", "extra_attrs", "notes")

    def __init__(self, kind: str, line: int) -> None:
        self.kind = kind
        self.line = line
        self.fields: List[Tuple[str, object]] = []
        self.properties: List[PropertyEntry] = []
        self.attributes: List[PropertyEntry] = []
        self.slots: Dict[str, List[_Built]] = {}
        self.extra_attrs: List[Tuple[str, str]] = []
        self.notes: List[_Note] = []

    def add_slot(self, name: str, child: "_Built") -> None:
        self.slots.setdefault(name, []).append(child)

    def field_map(self) -> Dict[str, object]:
        return dict(self.fields)

    def set_field(self, name: str, value: object) -> None:
        self.fields = [(key, item) for key, item in self.fields if key != name]
        self.fields.append((name, value))


class _ReadArena:
    """Reuse pools for one read at a time.

    Each ``read_ui`` call owns one arena from start to finish, so overlapping
    reads (other threads, or a nested read from an allocator or listener on the
    same thread) never share pooled objects. Each pool keeps at most
    ``_POOL_CAP`` objects.
    """

    __slots__ = ("xnode_pool", "xnode_live", "list_pool", "frame_pool", "built_pool", "built_live", "seen")

    def __init__(self) -> None:
        self.xnode_pool: List[_XNode] = []
        self.xnode_live: List[_XNode] = []
        self.list_pool: List[list] = []
        self.frame_pool: List[list] = []
        self.built_pool: List[_Built] = []
        self.built_live: List[_Built] = []
        self.seen: List[str] = []

    def take_list(self) -> list:
        pool = self.list_pool
        if pool:
            return pool.pop()
        return []

    def take_built(self, kind: str, line: int) -> _Built:
        pool = self.built_pool
        if pool:
            built = pool.pop()
            built.kind = kind
            built.line = line
            built.fields.clear()
            built.properties.clear()
            built.attributes.clear()
            built.slots.clear()
            built.extra_attrs.clear()
            built.notes.clear()
        else:
            built = _Built(kind, line)
        self.built_live.append(built)
        return built

    def release_xnodes(self) -> None:
        """Return this read's elements to the pool without walking the tree."""
        live = self.xnode_live
        if not live:
            return
        lists = self.list_pool
        cap = _POOL_CAP
        for node in live:
            children = node.children
            node.children = _NO_CHILDREN
            node.attrs = _NO_ATTRS
            node.tag = ""
            if isinstance(children, list):
                children.clear()
                if len(lists) < cap:
                    lists.append(children)
        pool = self.xnode_pool
        room = cap - len(pool)
        if room >= len(live):
            pool.extend(live)
        elif room > 0:
            pool.extend(live[:room])
        del live[:]

    def release_built(self) -> None:
        live = self.built_live
        if not live:
            return
        for built in live:
            built.fields.clear()
            built.properties.clear()
            built.attributes.clear()
            built.slots.clear()
            built.extra_attrs.clear()
            built.notes.clear()
        pool = self.built_pool
        room = _POOL_CAP - len(pool)
        if room >= len(live):
            pool.extend(live)
        elif room > 0:
            pool.extend(live[:room])
        del live[:]

    def reset(self) -> None:
        self.release_xnodes()
        self.release_built()
        self.seen.clear()


_ARENA_LOCK = threading.Lock()
_ARENA_FREE: List[_ReadArena] = []
# A realistic form allocates thousands of tracked tuples. Left alone, that
# promotes a full gen2 scan into the timed read and blows the 25 ms budget.
# Collections are paused for the outermost read and one generation is drained
# after the tree is built, so the scan stays in gen0 or gen1.
_GC_LOCK = threading.Lock()
_GC_DEPTH = 0
_GC_WAS_ON = True
#: Idle arenas kept for reuse. More concurrent reads than this get fresh arenas.
_ARENA_FREE_CAP = 4


def _pause_collections() -> None:
    global _GC_DEPTH, _GC_WAS_ON
    with _GC_LOCK:
        if _GC_DEPTH == 0:
            _GC_WAS_ON = gc.isenabled()
            if _GC_WAS_ON:
                gc.disable()
        _GC_DEPTH += 1


def _resume_collections() -> None:
    global _GC_DEPTH
    with _GC_LOCK:
        _GC_DEPTH -= 1
        if _GC_DEPTH > 0 or not _GC_WAS_ON:
            return
        gc.enable()
        counts = gc.get_count()
        thresholds = gc.get_threshold()
        if counts[2] >= thresholds[2]:
            generation = 2
        elif counts[1] >= thresholds[1]:
            generation = 1
        elif counts[0] >= thresholds[0]:
            generation = 0
        else:
            generation = -1
    if generation >= 0:
        gc.collect(generation)


def _intern_push() -> None:
    state = getattr(_INTERN, "state", None)
    if state is None:
        state = [0, {}]
        _INTERN.state = state
    state[0] += 1


def _intern_pop() -> None:
    state = _INTERN.state
    state[0] -= 1
    if state[0] == 0:
        state[1].clear()


_ShareT = TypeVar("_ShareT")


def _share(value: _ShareT) -> _ShareT:
    """Return the first equal frozen value built during this read."""
    state = getattr(_INTERN, "state", None)
    if state is None or not state[0]:
        return value
    cache = state[1]
    try:
        found = cache.get(value)
    except TypeError:
        return value
    if found is not None:
        return found
    cache[value] = value
    return value


def _acquire_arena() -> _ReadArena:
    with _ARENA_LOCK:
        if _ARENA_FREE:
            return _ARENA_FREE.pop()
    return _ReadArena()


def _release_arena(arena: _ReadArena) -> None:
    try:
        arena.reset()
    except Exception:
        # A half-reset arena is dropped, never reused. KeyboardInterrupt and
        # SystemExit still propagate; the arena is simply never returned.
        return
    with _ARENA_LOCK:
        if len(_ARENA_FREE) < _ARENA_FREE_CAP:
            _ARENA_FREE.append(arena)


def _newline_of(text: str) -> str:
    """``\\r\\n`` only when every line ending in ``text`` is CRLF.

    A bare LF keeps the default. Designer rewrites a CRLF file with CRLF on
    every line and leaves an LF file as LF.
    """
    if "\r\n" not in text:
        return "\n"
    if "\n" in text.replace("\r\n", ""):
        return "\n"
    return "\r\n"


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
    * Only ``UiReadError`` escapes for bad input (section 8.1). Safe to call
      from several threads at once, and re-entrantly.
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
    arena = _acquire_arena()
    _intern_push()
    _pause_collections()
    try:
        root = _parse_tree(arena, text)
        built = _lower_ui(arena, root)
        arena.release_xnodes()
        line_map: Dict[NodeId, int] = {}
        diagnostics: List[FormDiagnostic] = []
        ui = _to_node(built, allocator, line_map, diagnostics, None, None, 0)
        arena.release_built()
        document = UiDocument(ui)
        document.newline = _newline_of(text)
        document._check_validate()
        diagnostics.extend(_form_cell_warnings(document, line_map))
    except UiReadError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except RecursionError as exc:
        raise UiReadError(
            "FB008",
            "This form is nested too deeply to open in the form builder.",
            0,
            0,
        ) from exc
    except Exception as exc:
        raise UiReadError(
            "FB001",
            "This form is not valid XML (%s)." % (type(exc).__name__,),
            0,
            0,
        ) from exc
    finally:
        _intern_pop()
        _release_arena(arena)
        _resume_collections()
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


def _parse_tree(arena: _ReadArena, text: str) -> _XNode:
    parser = expat.ParserCreate()
    parser.ordered_attributes = True
    parser.buffer_text = True
    stack: List[List[object]] = []
    root: List[Optional[_XNode]] = [None]
    # The handlers run per element, so they bind this read's pools locally.
    list_pool = arena.list_pool
    frame_pool = arena.frame_pool
    xnode_pool = arena.xnode_pool
    xnode_live = arena.xnode_live
    cap = _POOL_CAP

    def take_list() -> list:
        if list_pool:
            return list_pool.pop()
        return []

    def take_frame(name: str, pairs: Tuple[Tuple[str, str], ...], line: int) -> list:
        if frame_pool:
            frame = frame_pool.pop()
            frame[0] = name
            frame[1] = pairs
            frame[2] = line
            return frame
        return [name, pairs, line, take_list()]

    def _position() -> Tuple[int, int]:
        return parser.CurrentLineNumber, parser.CurrentColumnNumber + 1

    def start(name: str, attrs: List[str]) -> None:
        if len(stack) >= MAX_DEPTH:
            line, column = _position()
            raise UiReadError("FB008", "This form is nested too deeply to open in the form builder.", line, column)
        count = len(attrs)
        if count == 0:
            pairs: Tuple[Tuple[str, str], ...] = _NO_ATTRS
        elif count == 2:
            pairs = ((attrs[0], attrs[1]),)
        elif count == 4:
            pairs = ((attrs[0], attrs[1]), (attrs[2], attrs[3]))
        else:
            built_pairs = []
            for index in range(0, count, 2):
                built_pairs.append((attrs[index], attrs[index + 1]))
            pairs = tuple(built_pairs)
        stack.append(take_frame(name, pairs, parser.CurrentLineNumber))

    def end(name: str) -> None:
        del name
        frame = stack.pop()
        tag, attrs, line, parts = frame
        children = _coalesce(parts)
        if children is not parts and len(list_pool) < cap:
            parts.clear()
            list_pool.append(parts)
        frame[3] = take_list()
        if len(frame_pool) < 128:
            frame_pool.append(frame)
        if xnode_pool:
            node = xnode_pool.pop()
            node.tag = tag
            node.attrs = attrs
            node.children = children
            node.line = line
        else:
            node = _XNode(tag, attrs, children, line)
        xnode_live.append(node)
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


def _coalesce(parts: List[object]) -> Sequence[object]:
    """Join adjacent text. ``buffer_text`` already joins most runs, so the
    common shapes (nothing, one child, or elements with no adjacent text)
    keep the parser's list instead of copying it into a tuple."""
    count = len(parts)
    if count < 2:
        return parts
    previous_text = isinstance(parts[0], str)
    for index in range(1, count):
        this_text = isinstance(parts[index], str)
        if this_text and previous_text:
            return _merge_text(parts)
        previous_text = this_text
    return parts


def _merge_text(parts: List[object]) -> List[object]:
    merged: List[object] = []
    for part in parts:
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] = merged[-1] + part
        else:
            merged.append(part)
    return merged


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


def _lower_ui(arena: "_ReadArena", node: _XNode) -> _Built:
    if node.tag != "ui":
        raise UiReadError("FB002", "This file is not a form.", node.line, 0)
    built = arena.take_built("ui", node.line)
    _apply_attrs(built, node.attrs)
    version = built.field_map().get("version")
    if not (isinstance(version, str) and version.split(".")[0] == "4"):
        shown = version if isinstance(version, str) else ""
        built.notes.append(_Note("FB003", 'This form says version "%s". The form builder expects 4.x.' % shown, node.line))
    cursor = _Cursor()
    wrappers: set = set()
    # Whole wrapper elements kept opaque (unknown attributes). Those already
    # write the tag, so the empty-wrapper pin must not emit a second copy.
    suppressed: set = set()
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                built.add_slot("opaque", _text_opaque(arena, child, cursor.here(), node.line))
            continue
        if isinstance(child, (OpaqueComment, OpaquePI)):
            continue
        if not isinstance(child, _XNode):
            continue
        group = _ui_group(child.tag)
        if group is None:
            built.add_slot("opaque", _opaque_built(arena, child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
            continue
        _place_ui_child(arena, built, child, wrappers, cursor, group, suppressed)
    if "root" not in built.slots:
        raise UiReadError("FB002", "This form has no root widget.", node.line, 0)
    # Appendix E: Designer always writes these two, even when the source omitted them.
    for tag in ("resources", "connections"):
        if tag not in suppressed:
            wrappers.add(tag)
    built.set_field("present_wrappers", frozenset(wrappers))
    _order_fields(built)
    return built


def _ui_group(tag: str) -> Optional[str]:
    return _UI_CHILD_GROUP.get(tag)


def _place_ui_child(
    arena: "_ReadArena",
    built: _Built,
    child: _XNode,
    wrappers: set,
    cursor: _Cursor,
    group: str,
    suppressed: set,
) -> None:
    tag = child.tag
    if tag in ("author", "comment", "exportmacro", "pixmapfunction"):
        # Appendix E omits empty author, comment, and exportmacro. A non-empty
        # value, or one with attributes, stays.
        if tag != "pixmapfunction" and _text_leaf(child) == "":
            cursor.advance(group)
            return
        _set_text_field(built, tag, child)
        cursor.advance(group)
        return
    if tag == "class":
        _set_text_field(built, "class_name", child)
        cursor.advance(group)
        return
    if tag == "widget":
        if "root" in built.slots:
            built.add_slot("opaque", _opaque_built(arena, child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept an extra root widget.", child.line))
            return
        built.add_slot("root", _lower_widget(arena, child))
        cursor.advance("root")
        return
    if tag == "layoutdefault":
        _set_parsed_field(built, "layoutdefault", child, _layout_default(child))
        cursor.advance(group)
        return
    if tag == "layoutfunction":
        _set_parsed_field(built, "layoutfunction", child, _layout_function(child))
        cursor.advance(group)
        return
    if tag == "tabstops":
        _set_parsed_field(built, "tabstops", child, _tabstops(child))
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
        _set_parsed_field(built, "form_slots", child, _slots_decl(child))
        cursor.advance(group)
        return
    if tag in ("customwidgets", "includes", "resources", "connections", "buttongroups"):
        count = _lower_wrapper(arena, built, child, tag, wrappers, suppressed)
        cursor.enter(group, count)
        return


def _lower_wrapper(
    arena: "_ReadArena",
    built: _Built,
    node: _XNode,
    tag: str,
    wrappers: set,
    suppressed: set,
) -> int:
    slot = _WRAPPER_SLOT[tag]
    if tag == "resources":
        # Appendix E drops the name attribute. Includes stay typed resource nodes.
        kept = tuple(pair for pair in node.attrs if pair[0] != "name")
        if len(kept) != len(node.attrs):
            node.attrs = kept
    if node.attrs:
        suppressed.add(tag)
        wrappers.discard(tag)
        built.add_slot("opaque", _opaque_built(arena, node, (slot, 0)))
        built.notes.append(_Note("FB006", "Kept attributes on <%s>." % tag, node.line))
        return 0
    wrappers.add(tag)
    typed = 0
    for child in _elements(node):
        lowered = _lower_known(arena, child, tag)
        if lowered is None:
            built.add_slot("opaque", _opaque_built(arena, child, ("%s:inner" % slot, typed)))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
        else:
            built.add_slot(slot, lowered)
            typed += 1
    return typed


def _lower_known(arena: "_ReadArena", node: _XNode, parent_tag: str) -> Optional[_Built]:
    if parent_tag == "customwidgets" and node.tag == "customwidget":
        return _lower_custom(arena, node)
    if parent_tag == "includes" and node.tag == "include":
        return _lower_include(arena, node)
    if parent_tag == "resources" and node.tag == "include":
        return _lower_resource(arena, node)
    if parent_tag == "connections" and node.tag == "connection":
        return _lower_connection(arena, node)
    if parent_tag == "buttongroups" and node.tag == "buttongroup":
        return _lower_named_box(arena, node, "buttongroup")
    return None


def _lower_widget(arena: "_ReadArena", node: _XNode) -> _Built:
    return _lower_box(arena, node, "widget")


def _lower_box(arena: "_ReadArena", node: _XNode, kind: str) -> _Built:
    if kind == "widget":
        fast = _lower_property_widget(arena, node)
        if fast is not None:
            return fast
    elif kind == "layout":
        fast = _lower_item_layout(arena, node)
        if fast is not None:
            return fast
    elif kind == "layoutitem":
        fast = _lower_single_content_item(arena, node)
        if fast is not None:
            return fast
    built = arena.take_built(kind, node.line)
    _apply_attrs(built, node.attrs)
    _ensure_required(built)
    cursor = _Cursor()
    properties: List[Tuple[PropertyEntry, _XNode, List[_Note]]] = []
    attributes: List[Tuple[PropertyEntry, _XNode, List[_Note]]] = []
    prop_stream: List[Tuple[str, object]] = []
    attr_stream: List[Tuple[str, object]] = []
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                _hold_gap(arena, built, cursor, prop_stream, attr_stream, ("gap-text", (child, node.line)))
            continue
        if not isinstance(child, _XNode):
            continue
        group = _box_group(kind, child.tag, built)
        if group == "layout" and "layout" in built.slots:
            built.add_slot("opaque", _opaque_built(arena, child, cursor.here()))
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
            _hold_gap(arena, built, cursor, prop_stream, attr_stream, ("gap-node", child))
            continue
        _place_box_child(arena, built, child, group)
        cursor.advance(group)
    _realize_entries(arena, built, properties, prop_stream, "properties")
    _realize_entries(arena, built, attributes, attr_stream, "attributes")
    if kind == "header" and not built.field_map().get("axis"):
        built.set_field("axis", "row")
    _order_fields(built)
    return built


def _lower_property_widget(arena: "_ReadArena", node: _XNode) -> Optional[_Built]:
    """Widget whose element children are only ``<property>``. Other shapes
    (a layout, a child widget, stray text) use the general lowerer."""
    props: List[_XNode] = []
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                return None
            continue
        if not isinstance(child, _XNode):
            continue
        if child.tag != "property":
            return None
        props.append(child)
    built = arena.take_built("widget", node.line)
    _apply_attrs(built, node.attrs)
    _ensure_required(built)
    seen = arena.seen
    seen.clear()
    properties = built.properties
    for child in props:
        entry, notes = _parse_property(child, "property")
        if entry.name in seen:
            return None
        seen.append(entry.name)
        properties.append(entry)
        if notes:
            built.notes.extend(notes)
    _order_fields(built)
    return built


def _lower_item_layout(arena: "_ReadArena", node: _XNode) -> Optional[_Built]:
    """Layout whose element children are only ``<item>``."""
    items: List[_XNode] = []
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                return None
            continue
        if not isinstance(child, _XNode):
            continue
        if child.tag != "item":
            return None
        items.append(child)
    built = arena.take_built("layout", node.line)
    _apply_attrs(built, node.attrs)
    _ensure_required(built)
    if items:
        built.slots["layout_items"] = [_lower_box(arena, child, "layoutitem") for child in items]
    _order_fields(built)
    return built


def _lower_single_content_item(arena: "_ReadArena", node: _XNode) -> Optional[_Built]:
    """Layout ``<item>`` with one widget, layout, or spacer and no stray text."""
    content: Optional[_XNode] = None
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                return None
            continue
        if not isinstance(child, _XNode):
            continue
        if content is not None:
            return None
        content = child
    if content is None:
        return None
    tag = content.tag
    if tag == "widget":
        lowered = _lower_box(arena, content, "widget")
    elif tag == "layout":
        lowered = _lower_box(arena, content, "layout")
    elif tag == "spacer":
        lowered = _lower_box(arena, content, "spacer")
    else:
        return None
    built = arena.take_built("layoutitem", node.line)
    _apply_attrs(built, node.attrs)
    _ensure_required(built)
    built.add_slot("content", lowered)
    _order_fields(built)
    return built


def _box_group(kind: str, tag: str, built: _Built) -> Optional[str]:
    spec = SCHEMA[kind]
    if tag == "property" and spec.has_properties:
        return "properties"
    if tag == "attribute" and spec.has_attributes:
        return "attributes"
    if kind == "widget":
        return _WIDGET_CHILD_GROUP.get(tag)
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


def _place_box_child(arena: "_ReadArena", built: _Built, child: _XNode, group: str) -> None:
    if group == "child:zorder":
        text = _text_leaf(child)
        current = built.field_map().get("zorder")
        names = list(current) if isinstance(current, tuple) else []
        if text is None:
            built.add_slot("opaque", _opaque_built(arena, child, ("child:zorder", len(names))))
            built.notes.append(_Note("FB006", "Kept <zorder> as written.", child.line))
            return
        names.append(text)
        built.set_field("zorder", tuple(names))
        return
    if group == "rows":
        header = _lower_box(arena, child, "header")
        header.set_field("axis", "row")
        built.add_slot("rows", header)
        return
    if group == "columns":
        header = _lower_box(arena, child, "header")
        header.set_field("axis", "column")
        built.add_slot("columns", header)
        return
    if group == "items":
        built.add_slot("items", _lower_box(arena, child, "item"))
        return
    if group == "subitems":
        built.add_slot("subitems", _lower_box(arena, child, "item"))
        return
    if group == "layout":
        built.add_slot("layout", _lower_box(arena, child, "layout"))
        return
    if group == "layout_items":
        built.add_slot("layout_items", _lower_box(arena, child, "layoutitem"))
        return
    if group == "content":
        if child.tag == "widget":
            built.add_slot("content", _lower_box(arena, child, "widget"))
        elif child.tag == "layout":
            built.add_slot("content", _lower_box(arena, child, "layout"))
        elif child.tag == "spacer":
            built.add_slot("content", _lower_box(arena, child, "spacer"))
        return
    if group == "children":
        built.add_slot("children", _lower_box(arena, child, "widget"))
        return
    if group == "actions":
        built.add_slot("actions", _lower_box(arena, child, "action"))
        return
    if group == "action_groups":
        built.add_slot("action_groups", _lower_box(arena, child, "actiongroup"))
        return
    if group == "add_actions":
        built.add_slot("add_actions", _lower_box(arena, child, "actionref"))


def _lower_custom(arena: "_ReadArena", node: _XNode) -> _Built:
    built = arena.take_built("customwidget", node.line)
    _apply_attrs(built, node.attrs)
    if built.extra_attrs:
        built.notes.append(_Note("FB006", "Kept attributes on <customwidget>.", node.line))
    cursor = _Cursor()
    for child in _elements(node):
        tag = child.tag
        if tag == "class":
            _set_text_field(built, "class_name", child)
            cursor.advance("child:class")
        elif tag == "extends":
            _set_text_field(built, "extends", child)
            cursor.advance("child:extends")
        elif tag == "header":
            _set_parsed_field(built, "header", child, _header_decl(child))
            cursor.advance("child:header")
        elif tag == "sizehint":
            _set_parsed_field(built, "sizehint", child, _size_hint(child))
            cursor.advance("child:sizehint")
        elif tag == "addpagemethod":
            _set_text_field(built, "addpagemethod", child)
            cursor.advance("child:addpagemethod")
        elif tag == "container":
            text = _text_leaf(child)
            number = None if text is None else _parse_int(text, _INT32)
            _set_parsed_field(built, "container", child, number)
            cursor.advance("child:container")
        elif tag == "pixmap":
            _set_text_field(built, "pixmap", child)
            cursor.advance("child:pixmap")
        elif tag == "slots":
            _set_parsed_field(built, "slots", child, _slots_decl(child))
            cursor.advance("child:slots")
        elif tag == "propertyspecifications":
            built.set_field("propertyspecifications", _to_opaque(child))
            cursor.advance("child:propertyspecifications")
        else:
            built.add_slot("opaque", _opaque_built(arena, child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % tag, child.line))
    if "class_name" not in built.field_map():
        built.set_field("class_name", "")
    if "extends" not in built.field_map():
        built.set_field("extends", "")
    _order_fields(built)
    return built


def _lower_include(arena: "_ReadArena", node: _XNode) -> _Built:
    built = arena.take_built("include", node.line)
    _apply_attrs(built, node.attrs)
    text = _exact_text(node)
    if text:
        built.set_field("text", text)
    _order_fields(built)
    return built


def _lower_resource(arena: "_ReadArena", node: _XNode) -> _Built:
    built = arena.take_built("resource", node.line)
    _apply_attrs(built, node.attrs)
    if "location" not in built.field_map():
        built.set_field("location", "")
    _order_fields(built)
    return built


def _lower_connection(arena: "_ReadArena", node: _XNode) -> _Built:
    built = arena.take_built("connection", node.line)
    _apply_attrs(built, node.attrs)
    if built.extra_attrs:
        built.notes.append(_Note("FB006", "Kept attributes on <connection>.", node.line))
    cursor = _Cursor()
    for child in _elements(node):
        if child.tag in ("sender", "signal", "receiver", "slot"):
            _set_text_field(built, child.tag, child)
            cursor.advance("child:" + child.tag)
        elif child.tag == "hints":
            _set_parsed_field(built, "hints", child, _connection_hints(child))
            cursor.advance("child:hints")
        else:
            built.add_slot("opaque", _opaque_built(arena, child, cursor.here()))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % child.tag, child.line))
    for name in ("sender", "signal", "receiver", "slot"):
        if name not in built.field_map():
            built.set_field(name, "")
    _order_fields(built)
    return built


def _lower_named_box(arena: "_ReadArena", node: _XNode, kind: str) -> _Built:
    return _lower_box(arena, node, kind)


def _parse_property(node: _XNode, kind: str) -> Tuple[PropertyEntry, List[_Note]]:
    children = node.children
    attrs = node.attrs
    if len(children) == 1 and isinstance(children[0], _XNode):
        if len(attrs) == 1 and attrs[0][0] == "name":
            parsed = _parse_value(children[0])
            if parsed is not None:
                return _share(PropertyEntry(kind=kind, name=attrs[0][1], value=_share(parsed))), _NO_NOTES
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
        parsed = _parse_value(children[0])
        if parsed is not None:
            return (
                _share(PropertyEntry(
                    kind=kind,
                    name=name,
                    value=_share(parsed),
                    stdset=stdset,
                    extra_attrs=tuple(extra) if extra else _NO_ATTRS,
                )),
                _NO_NOTES,
            )
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
        value = OpaqueValue(_property_content(node))
        notes.append(_Note("FB005", "Kept this property value as written.", node.line, name or None))
    else:
        parsed = _parse_value(elements[0])
        if parsed is None:
            value = OpaqueValue(_to_opaque(elements[0]))
            notes.append(_Note("FB005", "Kept this <%s> value as written." % elements[0].tag, elements[0].line, name or None))
        else:
            value = parsed
    return _share(PropertyEntry(kind=kind, name=name, value=_share(value), stdset=stdset, extra_attrs=tuple(extra))), notes


def _hold_gap(
    arena: "_ReadArena",
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
            built.add_slot("opaque", _text_opaque(arena, text, cursor.here(), line))
        return
    if isinstance(payload, _XNode):
        built.add_slot("opaque", _opaque_built(arena, payload, cursor.here()))
        built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % payload.tag, payload.line))


def _realize_entries(
    arena: "_ReadArena",
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
                built.add_slot("opaque", _opaque_built(arena, source, (group, typed_so_far)))
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
                built.add_slot("opaque", _text_opaque(arena, text, (group, typed_so_far), line))
            continue
        if kind == "gap-node" and isinstance(payload, _XNode):
            built.add_slot("opaque", _opaque_built(arena, payload, (group, typed_so_far)))
            built.notes.append(_Note("FB006", "Kept the unknown element <%s>." % payload.tag, payload.line))
    if group == "properties":
        built.properties = typed
    else:
        built.attributes = typed


def _parse_value(node: _XNode) -> Optional[Value]:
    tag = _INT_TAG_ALIASES.get(node.tag, node.tag)
    if tag == "string":
        return _parse_string(node)
    if tag == "font":
        return _parse_font(node)
    if tag == "size":
        return _int_record(node, SizeValue, ("width", "height"))
    if tag == "sizepolicy":
        return _parse_sizepolicy(node)
    if tag == "number":
        return _parse_counted(node, NumberValue, _INT32)
    if tag == "pixmap":
        return _parse_pixmap_element(node)
    if tag == "iconset":
        return _parse_iconset(node)
    if tag == "brush":
        return _parse_brush(node)
    if tag == "palette":
        return _parse_palette(node)
    if tag not in VALUE_CLASSES and tag not in _CURSOR_SHAPE_TAGS:
        return None
    if tag == "bool":
        text = _text_leaf(node)
        if text == "true":
            return BoolValue(True)
        if text == "false":
            return BoolValue(False)
        return None
    if tag in _INT_LIMITS:
        return _parse_counted(node, VALUE_CLASSES[tag], _INT_LIMITS[tag])
    if tag in ("double", "float"):
        text = _text_leaf(node)
        value = None if text is None else _lossless_real(text, tag)
        if value is None:
            return None
        if tag == "double":
            return DoubleValue(value)
        return FloatValue(value)
    if tag == "cstring":
        if node.attrs or not _is_plain(node):
            return None
        return CStringValue(_exact_text(node))
    if tag in ("enum", "set") or tag in _CURSOR_SHAPE_TAGS:
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
    if tag == "sizef":
        return _real_record(node, SizeFValue, ("width", "height"))
    if tag == "point":
        return _int_record(node, PointValue, ("x", "y"))
    if tag == "pointf":
        return _real_record(node, PointFValue, ("x", "y"))
    if tag == "char":
        return _parse_char(node)
    if tag == "color":
        return _parse_color(node)
    if tag == "date":
        return _int_record(node, DateValue, ("year", "month", "day"))
    if tag == "time":
        return _int_record(node, TimeValue, ("hour", "minute", "second"))
    if tag == "datetime":
        return _int_record(node, DateTimeValue, ("hour", "minute", "second", "year", "month", "day"))
    if tag == "locale":
        attrs = _known_attrs(node, frozenset({"language", "country"}))
        if attrs is None or "language" not in attrs or "country" not in attrs:
            return None
        return LocaleValue(attrs["language"], attrs["country"])
    if tag == "url":
        if node.attrs or _has_noise(node):
            return None
        children = _elements(node)
        if len(children) != 1 or children[0].tag != "string":
            return None
        parsed = _parse_string(children[0])
        if parsed is None:
            return None
        return UrlValue(parsed)
    return None


def _parse_counted(node: _XNode, cls: type, limits: Tuple[int, int]) -> Optional[Value]:
    if node.attrs:
        return None
    text = _one_text(node)
    if text is None:
        return None
    number = _parse_int(text, limits)
    if number is None:
        return None
    return cls(number)  # type: ignore[call-arg, no-any-return]


def _parse_string(node: _XNode) -> Optional[StringValue]:
    text = _one_text(node)
    if text is None:
        return None
    if not node.attrs:
        return StringValue(text)
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
    return StringValue(text, notr, comment, extracomment, string_id)


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


def _policy_token(text: str) -> Optional[str]:
    mapped = _POLICY_BY_INT.get(text)
    if mapped is not None:
        return mapped
    if text.isdigit() or not text:
        return None
    return text


def _parse_sizepolicy(node: _XNode) -> Optional[SizePolicyValue]:
    attrs = node.attrs
    children = node.children
    if (
        len(attrs) == 2
        and attrs[0][0] == "hsizetype"
        and attrs[1][0] == "vsizetype"
        and attrs[0][1]
        and attrs[1][1]
        and len(children) == 2
        and isinstance(children[0], _XNode)
        and isinstance(children[1], _XNode)
        and children[0].tag == "horstretch"
        and children[1].tag == "verstretch"
        and not children[0].attrs
        and not children[1].attrs
    ):
        hor_text = _one_text(children[0])
        ver_text = _one_text(children[1])
        if hor_text is not None and ver_text is not None:
            horstretch = _parse_int(hor_text, _INT32)
            verstretch = _parse_int(ver_text, _INT32)
            if horstretch is not None and verstretch is not None:
                return SizePolicyValue(attrs[0][1], attrs[1][1], horstretch, verstretch)
    if _has_comment(node) or _has_significant_text(node):
        return None
    attrs = _attr_map(node, frozenset({"hsizetype", "vsizetype"}))
    if attrs is None:
        return None
    horizontal = attrs.get("hsizetype")
    vertical = attrs.get("vsizetype")
    horstretch = 0
    verstretch = 0
    for child in _elements(node):
        leaf = _text_leaf(child)
        if leaf is None:
            return None
        text = leaf.strip()
        if child.tag in ("hsizetype", "vsizetype"):
            name = _policy_token(text)
            current = horizontal if child.tag == "hsizetype" else vertical
            if name is None or (current is not None and current != name):
                return None
            if child.tag == "hsizetype":
                horizontal = name
            else:
                vertical = name
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
    fast = _parse_font_fast(node)
    if fast is not _MISS:
        return fast  # type: ignore[return-value]
    if node.attrs or _has_noise(node):
        return None
    values: Dict[str, object] = {}
    for child in _elements(node):
        if child.attrs or _has_comment(child) or child.tag in values or child.tag not in _FONT_INT | _FONT_BOOL | _FONT_TEXT:
            return None
        if child.tag in _FONT_INT:
            if not _is_plain(child):
                return None
            number = _parse_int(_exact_text(child), _INT32)
            if number is None:
                return None
            values[child.tag] = number
        elif child.tag in _FONT_BOOL:
            if not _is_plain(child):
                return None
            text = _exact_text(child)
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


def _parse_char(node: _XNode) -> Optional[CharValue]:
    if node.attrs or _has_noise(node):
        return None
    children = _elements(node)
    if len(children) != 1 or children[0].tag != "unicode":
        return None
    text = _text_leaf(children[0])
    number = None if text is None else _parse_int(text, _INT32)
    if number is None:
        return None
    return CharValue(number)


def _parse_color(node: _XNode) -> Optional[ColorValue]:
    if _has_comment(node) or _has_significant_text(node):
        return None
    attrs = _attr_map(node, frozenset({"alpha"}))
    if attrs is None:
        return None
    found: Dict[str, int] = {}
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None or child.tag in found or child.tag not in ("red", "green", "blue"):
            return None
        number = _parse_int(text, _INT32)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != {"red", "green", "blue"}:
        return None
    alpha = None
    if "alpha" in attrs:
        alpha = _parse_int(attrs["alpha"], _INT32)
        if alpha is None:
            return None
    return ColorValue(found["red"], found["green"], found["blue"], alpha)


def _parse_pixmap_element(node: _XNode) -> Optional[ResourcePixmap]:
    if not _is_plain(node) or _has_comment(node):
        return None
    attrs = _attr_map(node, frozenset({"resource", "alias"}))
    if attrs is None:
        return None
    return ResourcePixmap(path=_exact_text(node), resource=attrs.get("resource"), alias=attrs.get("alias"))


def _later_icon_state(children: Sequence[object], start: int) -> bool:
    """True when another icon state element follows, ignoring whitespace."""
    index = start
    while index < len(children):
        child = children[index]
        if isinstance(child, str):
            if child.strip():
                return False
            index += 1
            continue
        return isinstance(child, _XNode) and child.tag in ICON_STATES
    return False


def _parse_iconset(node: _XNode) -> Optional[IconSetValue]:
    attrs = _attr_map(node, frozenset({"theme", "resource"}))
    if attrs is None or _has_comment(node):
        return None
    states: Dict[str, ResourcePixmap] = {}
    leading: List[str] = []
    trailing: List[str] = []
    saw_state = False
    children = list(node.children)
    index = 0
    while index < len(children):
        child = children[index]
        if isinstance(child, str):
            if not saw_state:
                leading.append(child)
                index += 1
                continue
            # A trailer that matches the state just read is the old per-state
            # form. Text after the last state is Designer's single compat path.
            if _later_icon_state(children, index + 1):
                last = next(reversed(states.values()))
                if child.strip() and child.strip() != last.path:
                    return None
                index += 1
                continue
            trailing.append(child)
            index += 1
            continue
        if trailing and any(part.strip() for part in trailing):
            return None
        if not isinstance(child, _XNode) or child.tag not in ICON_STATES or child.tag in states:
            return None
        pixmap = _parse_pixmap_element(child)
        if pixmap is None:
            return None
        states[child.tag] = pixmap
        saw_state = True
        trailing.clear()
        index += 1
    if saw_state and any(part.strip() for part in leading):
        return None
    text = None
    if saw_state:
        compat = "".join(trailing).strip()
        if compat:
            text = compat
    else:
        exact = "".join(leading)
        if exact.strip():
            text = exact
    return IconSetValue(
        theme=attrs.get("theme"),
        resource=attrs.get("resource"),
        text=text,
        normaloff=states.get("normaloff"),
        normalon=states.get("normalon"),
        disabledoff=states.get("disabledoff"),
        disabledon=states.get("disabledon"),
        activeoff=states.get("activeoff"),
        activeon=states.get("activeon"),
        selectedoff=states.get("selectedoff"),
        selectedon=states.get("selectedon"),
    )


def _parse_brush(node: _XNode) -> Optional[BrushValue]:
    if _has_noise(node):
        return None
    attrs = _attr_map(node, frozenset({"brushstyle"}))
    if attrs is None:
        return None
    color: Optional[ColorValue] = None
    texture: Optional[ResourcePixmap] = None
    texture_name: Optional[str] = None
    gradient: Optional[GradientValue] = None
    for child in _elements(node):
        if color is not None or texture is not None or gradient is not None:
            return None
        if child.tag == "color":
            color = _parse_color(child)
            if color is None:
                return None
        elif child.tag == "texture":
            parsed = _parse_texture(child)
            if parsed is None:
                return None
            texture, texture_name = parsed
        elif child.tag == "gradient":
            gradient = _parse_gradient(child)
            if gradient is None:
                return None
        else:
            return None
    return BrushValue(
        brushstyle=attrs.get("brushstyle"),
        color=color,
        texture=texture,
        gradient=gradient,
        texture_name=texture_name,
    )


def _parse_texture(node: _XNode) -> Optional[Tuple[ResourcePixmap, Optional[str]]]:
    if _has_noise(node):
        return None
    attrs = _attr_map(node, frozenset({"name"}))
    if attrs is None:
        return None
    elements = _elements(node)
    if len(elements) != 1 or elements[0].tag != "pixmap":
        return None
    pixmap = _parse_pixmap_element(elements[0])
    if pixmap is None:
        return None
    return pixmap, attrs.get("name")


def _parse_gradient(node: _XNode) -> Optional[GradientValue]:
    if _has_noise(node):
        return None
    attrs = _attr_map(node, _GRADIENT_TEXT_ATTRS | _GRADIENT_REAL_ATTRS)
    if attrs is None:
        return None
    text_attrs: Dict[str, str] = {}
    real_attrs: Dict[str, float] = {}
    for key, value in attrs.items():
        if key in _GRADIENT_TEXT_ATTRS:
            text_attrs[key] = value
            continue
        number = _lossless_real(value)
        if number is None:
            return None
        real_attrs[key] = number
    stops: List[GradientStop] = []
    for child in _elements(node):
        if child.tag not in _GRADIENT_STOP_TAGS:
            return None
        stop = _parse_gradient_stop(child)
        if stop is None:
            return None
        stops.append(stop)
    return GradientValue(
        type=text_attrs.get("type"),
        spread=text_attrs.get("spread"),
        coordinatemode=text_attrs.get("coordinatemode"),
        startx=real_attrs.get("startx"),
        starty=real_attrs.get("starty"),
        endx=real_attrs.get("endx"),
        endy=real_attrs.get("endy"),
        centralx=real_attrs.get("centralx"),
        centraly=real_attrs.get("centraly"),
        focalx=real_attrs.get("focalx"),
        focaly=real_attrs.get("focaly"),
        radius=real_attrs.get("radius"),
        angle=real_attrs.get("angle"),
        stops=tuple(stops),
    )


def _parse_gradient_stop(node: _XNode) -> Optional[GradientStop]:
    if _has_noise(node):
        return None
    attrs = _attr_map(node, frozenset({"position"}))
    if attrs is None or "position" not in attrs:
        return None
    position = _lossless_real(attrs["position"])
    if position is None:
        return None
    elements = _elements(node)
    if len(elements) != 1 or elements[0].tag != "color":
        return None
    color = _parse_color(elements[0])
    if color is None:
        return None
    return GradientStop(position, color)


def _parse_palette(node: _XNode) -> Optional[PaletteValue]:
    if _has_noise(node) or node.attrs:
        return None
    found: Dict[str, Tuple[ColorRole, ...]] = {}
    for child in _elements(node):
        if child.tag not in _PALETTE_GROUPS or child.tag in found:
            return None
        roles = _parse_color_group(child)
        if roles is None:
            return None
        found[child.tag] = roles
    if set(found) != set(_PALETTE_GROUPS):
        return None
    return PaletteValue(active=found["active"], inactive=found["inactive"], disabled=found["disabled"])


def _parse_color_group(node: _XNode) -> Optional[Tuple[ColorRole, ...]]:
    if _has_noise(node) or node.attrs:
        return None
    # Qt applies every legacy <color> before any <colorrole>, and ignores
    # alpha on those legacy colors, with or without the attribute. A colorrole
    # brush with no alpha attribute loads as alpha 0, so every legacy color is
    # stored as 255: the opaque color Qt showed.
    legacy: List[ColorRole] = []
    explicit: List[ColorRole] = []
    legacy_index = 0
    for child in _elements(node):
        if child.tag == "colorrole":
            role = _parse_colorrole(child)
            if role is None:
                return None
            explicit.append(role)
            continue
        if child.tag != "color":
            return None
        if legacy_index >= len(_LEGACY_COLOR_ROLES):
            return None
        color = _parse_color(child)
        if color is None:
            return None
        color = ColorValue(color.red, color.green, color.blue, 255)
        legacy.append(
            ColorRole(
                _LEGACY_COLOR_ROLES[legacy_index],
                BrushValue(brushstyle="SolidPattern", color=color),
            )
        )
        legacy_index += 1
    return tuple(legacy + explicit)


def _parse_colorrole(node: _XNode) -> Optional[ColorRole]:
    if _has_noise(node):
        return None
    attrs = _attr_map(node, frozenset({"role"}))
    if attrs is None or not attrs.get("role"):
        return None
    elements = _elements(node)
    if len(elements) != 1 or elements[0].tag != "brush":
        return None
    brush = _parse_brush(elements[0])
    if brush is None:
        return None
    return ColorRole(attrs["role"], brush)


def _parse_font_fast(node: _XNode) -> object:
    if node.attrs:
        return _MISS
    values: Dict[str, object] = {}
    for child in node.children:
        if not isinstance(child, _XNode) or child.attrs or child.tag in values:
            return _MISS
        text = _one_text(child)
        if text is None:
            return _MISS
        tag = child.tag
        if tag in _FONT_INT:
            number = _parse_int(text, _INT32)
            if number is None:
                return None
            values[tag] = number
        elif tag in _FONT_BOOL:
            if text == "true":
                values[tag] = True
            elif text == "false":
                values[tag] = False
            else:
                return None
        elif tag in _FONT_TEXT:
            values[tag] = text
        else:
            return _MISS
    return FontValue(**values)  # type: ignore[arg-type]


def _int_record(node: _XNode, cls: type, names: Tuple[str, ...]) -> Optional[Value]:
    ordered = _ordered_ints(node, names)
    if ordered is not _MISS:
        if ordered is None:
            return None
        return cls(*ordered)  # type: ignore[operator, no-any-return]
    if node.attrs or _has_noise(node):
        return None
    found: Dict[str, int] = {}
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None or child.tag in found or child.tag not in names:
            return None
        number = _parse_int(text, _INT32)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != set(names):
        return None
    return cls(*(found[name] for name in names))  # type: ignore[no-any-return, operator]


def _real_record(node: _XNode, cls: type, names: Tuple[str, ...]) -> Optional[Value]:
    if node.attrs or _has_noise(node):
        return None
    found: Dict[str, float] = {}
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None or child.tag in found or child.tag not in names:
            return None
        number = _lossless_real(text)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != set(names):
        return None
    return cls(*(found[name] for name in names))  # type: ignore[no-any-return, operator]


def _layout_default(node: _XNode) -> Optional[LayoutDefault]:
    attrs = _known_attrs(node, frozenset({"spacing", "margin"}))
    if attrs is None:
        return None
    spacing = None
    margin = None
    if "spacing" in attrs:
        spacing = _parse_int(attrs["spacing"], _INT32)
        if spacing is None:
            return None
    if "margin" in attrs:
        margin = _parse_int(attrs["margin"], _INT32)
        if margin is None:
            return None
    return LayoutDefault(spacing, margin)


def _layout_function(node: _XNode) -> Optional[LayoutFunction]:
    attrs = _known_attrs(node, frozenset({"spacing", "margin"}))
    if attrs is None:
        return None
    return LayoutFunction(attrs.get("spacing"), attrs.get("margin"))


def _slots_decl(node: _XNode) -> Optional[SlotsDecl]:
    if node.attrs or _has_comment(node) or _has_significant_text(node):
        return None
    signals = []
    slots = []
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None:
            return None
        if child.tag == "signal":
            signals.append(text)
        elif child.tag == "slot":
            slots.append(text)
        else:
            return None
    return SlotsDecl(tuple(signals), tuple(slots))


def _tabstops(node: _XNode) -> Optional[Tuple[str, ...]]:
    if node.attrs or _has_comment(node) or _has_significant_text(node):
        return None
    names = []
    for child in _elements(node):
        if child.tag != "tabstop":
            return None
        text = _text_leaf(child)
        if text is None:
            return None
        names.append(text)
    return tuple(names)


def _header_decl(node: _XNode) -> Optional[HeaderDecl]:
    if _elements(node) or _has_comment(node):
        return None
    location = None
    for key, value in node.attrs:
        if key != "location" or location is not None:
            return None
        location = value
    return HeaderDecl(_exact_text(node), location)


def _size_hint(node: _XNode) -> Optional[SizeValue]:
    if node.attrs or _has_noise(node):
        return None
    found: Dict[str, int] = {}
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None or child.tag in found or child.tag not in ("width", "height"):
            return None
        number = _parse_int(text, _INT32)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != {"width", "height"}:
        return None
    return SizeValue(found["width"], found["height"])


def _connection_hints(node: _XNode) -> Optional[Tuple[ConnectionHint, ...]]:
    if node.attrs or _has_noise(node):
        return None
    hints = []
    for child in _elements(node):
        hint = _one_hint(child)
        if hint is None:
            return None
        hints.append(hint)
    return tuple(hints)


def _one_hint(node: _XNode) -> Optional[ConnectionHint]:
    if node.tag != "hint" or _has_noise(node):
        return None
    hint_type = ""
    seen_type = False
    for key, value in node.attrs:
        if key != "type" or seen_type:
            return None
        hint_type = value
        seen_type = True
    found: Dict[str, int] = {}
    for child in _elements(node):
        text = _text_leaf(child)
        if text is None or child.tag in found or child.tag not in ("x", "y"):
            return None
        number = _parse_int(text, _INT32)
        if number is None:
            return None
        found[child.tag] = number
    if set(found) != {"x", "y"}:
        return None
    return ConnectionHint(hint_type, found["x"], found["y"])


def _attr_map(node: _XNode, allowed: FrozenSet[str]) -> Optional[Dict[str, str]]:
    found: Dict[str, str] = {}
    for key, value in node.attrs:
        if key in found or key not in allowed:
            return None
        found[key] = value
    return found


def _known_attrs(node: _XNode, allowed: FrozenSet[str]) -> Optional[Dict[str, str]]:
    if _elements(node) or _has_comment(node) or _has_significant_text(node):
        return None
    return _attr_map(node, allowed)


def _one_text(node: _XNode) -> Optional[str]:
    """Exact character data when every child is text. None if an element, comment, or PI is present."""
    children = node.children
    count = len(children)
    if count == 1:
        child = children[0]
        if isinstance(child, str):
            return child
        return None
    if count == 0:
        return ""
    parts: List[str] = []
    for child in children:
        if not isinstance(child, str):
            return None
        parts.append(child)
    return "".join(parts)


def _ordered_ints(node: _XNode, names: Tuple[str, ...]) -> object:
    if node.attrs:
        return _MISS
    children = node.children
    count = len(names)
    if len(children) != count:
        return _MISS
    values = []
    for index in range(count):
        child = children[index]
        if not isinstance(child, _XNode) or child.tag != names[index] or child.attrs:
            return _MISS
        text = _one_text(child)
        if text is None:
            return _MISS
        number = _parse_int(text, _INT32)
        if number is None:
            return None
        values.append(number)
    return tuple(values)


def _text_leaf(node: _XNode) -> Optional[str]:
    if node.attrs:
        return None
    return _one_text(node)


def _set_text_field(built: _Built, field: str, node: _XNode) -> None:
    text = _text_leaf(node)
    if text is None:
        _keep_element(built, field, node)
    else:
        built.set_field(field, text)


def _set_parsed_field(built: _Built, field: str, node: _XNode, parsed: object) -> None:
    if parsed is None:
        _keep_element(built, field, node)
    else:
        built.set_field(field, parsed)


def _keep_element(built: _Built, field: str, node: _XNode) -> None:
    built.set_field(field, _to_opaque(node))
    built.notes.append(_Note("FB006", "Kept <%s> as written." % node.tag, node.line))


def _apply_attrs(built: _Built, attrs: Tuple[Tuple[str, str], ...]) -> None:
    known = _ATTR_FIELD[built.kind]
    fields = built.fields
    extra = built.extra_attrs
    for key, value in attrs:
        field_name = known.get(key)
        if field_name is None:
            extra.append((key, value))
            continue
        if field_name in _INT_ATTR_NAMES:
            number = _parse_int(value, _INT32)
            if number is None:
                extra.append((key, value))
            else:
                fields.append((field_name, number))
            continue
        fields.append((field_name, value))


def _ensure_required(built: _Built) -> None:
    required = _REQUIRED_FIELD[built.kind]
    if not required:
        return
    fields = built.fields
    for name in required:
        for key, _value in fields:
            if key == name:
                break
        else:
            built.set_field(name, "")


def _order_fields(built: _Built) -> None:
    built.fields.sort(key=_FIELD_KEY[built.kind])


def _to_node(
    built: _Built,
    allocator: IdAllocator,
    line_map: Dict[NodeId, int],
    diagnostics: List[FormDiagnostic],
    parent_id: Optional[NodeId],
    parent_slot: Optional[str],
    index: int,
) -> Node:
    node_id = DOCUMENT_ID if built.kind == "ui" else allocator.alloc()
    line_map[node_id] = built.line
    if built.notes:
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
    first = None
    extra_slots = None
    for slot in SCHEMA[built.kind].slots:
        kids = built.slots.get(slot.name)
        if not kids:
            continue
        item = (
            slot.name,
            tuple(
                _to_node(child, allocator, line_map, diagnostics, node_id, slot.name, child_index)
                for child_index, child in enumerate(kids)
            ),
        )
        if first is None:
            first = item
            continue
        if extra_slots is None:
            extra_slots = [first, item]
        else:
            extra_slots.append(item)
    if extra_slots is not None:
        slot_tuple = tuple(extra_slots)
    elif first is not None:
        slot_tuple = (first,)
    else:
        slot_tuple = _NO_SLOTS
    return build_node(
        kind=built.kind,
        node_id=node_id,
        parent_id=parent_id,
        parent_slot=parent_slot,
        slot_index=index,
        fields=tuple(built.fields) if built.fields else _NO_FIELDS,
        properties=tuple(built.properties) if built.properties else _NO_PROPS,
        attributes=tuple(built.attributes) if built.attributes else _NO_PROPS,
        slots=slot_tuple,
        extra_attrs=tuple(built.extra_attrs) if built.extra_attrs else _NO_ATTRS,
    )


def _form_cell_warnings(document: UiDocument, line_map: Dict[NodeId, int]) -> List[FormDiagnostic]:
    found: List[FormDiagnostic] = []
    for node in document.iter_preorder():
        if not isinstance(node, LayoutNode) or node.class_name != "QFormLayout":
            continue
        owners: Dict[Tuple[int, str], LayoutItemNode] = {}
        for item in node.items:
            cells = form_occupied_cells(item.row, item.column, item.colspan)
            taken = sorted((cell for cell in cells if cell in owners), key=lambda cell: cell[1] != "label")
            for cell in cells:
                owners.setdefault(cell, item)
            if not taken:
                continue
            row, word = taken[0]
            earlier = owners[taken[0]]
            spans = form_item_role(item.column, item.colspan) == "spanning"
            if spans and form_item_role(earlier.column, earlier.colspan) == "spanning":
                word = "spanning"
            found.append(
                FormDiagnostic(
                    code="FB023",
                    severity=Severity.WARNING,
                    message="Two widgets share the %s cell of row %s in %s." % (word, row, node.object_name),
                    location=DiagnosticLocation(
                        node_id=item.id,
                        object_name=_content_name(item),
                        line=line_map.get(item.id, 0),
                    ),
                    source="reader",
                )
            )
    return found


def _content_name(item: LayoutItemNode) -> Optional[str]:
    content = item.content
    if isinstance(content, (WidgetNode, LayoutNode)):
        return content.object_name or None
    if isinstance(content, SpacerNode):
        return content.name or None
    return None


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


def _opaque_built(arena: "_ReadArena", node: _XNode, anchor: Tuple[str, int]) -> _Built:
    built = arena.take_built("opaque", node.line)
    built.set_field("element", _to_opaque(node))
    built.set_field("anchor", anchor)
    return built


def _text_opaque(arena: "_ReadArena", text: str, anchor: Tuple[str, int], line: int) -> _Built:
    built = arena.take_built("opaque", line)
    built.set_field("element", OpaqueElement("", (), (text.strip(),)))
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
    if any(not isinstance(child, str) for child in children):
        children = [child for child in children if not isinstance(child, str) or child.strip()]
    return OpaqueElement(node.tag, node.attrs, tuple(children))


def _property_content(node: _XNode) -> OpaqueElement:
    """The property's own children, with no invented wrapper element.

    Indentation between those children is not content. A tag of ``""`` tells
    the writer to emit the children in place.
    """
    children: List[object] = []
    for child in node.children:
        if isinstance(child, str):
            stripped = child.strip()
            if stripped:
                children.append(stripped)
        elif isinstance(child, _XNode):
            children.append(_to_opaque(child))
        elif isinstance(child, (OpaqueComment, OpaquePI)):
            children.append(child)
    return OpaqueElement("", (), tuple(children))


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


def _ascii_int(text: str) -> Optional[int]:
    if not text:
        return None
    start = 1 if text[0] in "+-" else 0
    if start == len(text):
        return None
    for char in text[start:]:
        if char < "0" or char > "9":
            return None
    return int(text, 10)


def _parse_int(text: str, limits: Tuple[int, int]) -> Optional[int]:
    value = _ascii_int(text)
    if value is None and text != text.strip():
        value = _ascii_int(text.strip())
    if value is None or value < limits[0] or value > limits[1]:
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
