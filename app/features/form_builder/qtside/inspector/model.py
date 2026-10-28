
from __future__ import annotations

import dataclasses
import os
import weakref
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import (
    SetGeometry,
    SetLayoutCell,
    SetProperty,
    SetPropertyMany,
)
from app.features.form_builder.engine.events import ChangeSet, PropertyChanged
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import takes_layout
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.tree import effective_tab_order
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.defaults import PropertyInfo, QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    ActionNode,
    ConnectionNode,
    LayoutItemNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    ColorValue,
    CStringValue,
    CursorShapeValue,
    EnumValue,
    FontValue,
    PointValue,
    RectValue,
    SetValue,
    SizePolicyValue,
    SizeValue,
    StringListValue,
    StringValue,
    Value,
    semantic_equal,
)
from app.features.form_builder.qtside.inspector.api import (
    ALIGNMENT,
    EditorKey,
    EnumSpec,
    FlagBit,
    GROUP_ORDER,
    GroupId,
    LayoutProp,
    LockedRow,
    Match,
    Note,
    MatchWhere,
    Mixed,
    OpenRow,
    Prop,
    PropKind,
    Row,
    RowSpec,
    RowValue,
    RowWrite,
    Unset,
    ValueSpec,
    Written,
    editor_key,
)
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.features.form_builder.qtside.inspector.words import class_words, default_signal, event_words

SET_BY_LAYOUT = "Set by the layout."
SELECT_ONE_FOR_POSITION = "Select one widget to edit its position."
KEPT_AS_IS = "Kept as is"
NOT_SET = "\u2014"

LAYOUT_OWNED: FrozenSet[str] = frozenset({"geometry"})
_HEADER_OWNED: FrozenSet[str] = frozenset({"objectName"})

@dataclass(frozen=True)
class LiveProperty:
    name: str
    declared_by: str
    element: str
    enum: Optional[EnumSpec] = None
    value: Optional[Value] = None

@dataclass(frozen=True)
class LiveClass:

    chain: Tuple[str, ...]
    properties: Tuple[LiveProperty, ...]
    signals: Tuple[str, ...]
    slots: Tuple[str, ...]
    _by_name: Mapping[str, LiveProperty] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {prop.name: prop for prop in self.properties})

    def find(self, name: str) -> Optional[LiveProperty]:
        return self._by_name.get(name)

@dataclass(frozen=True)
class Facts:

    document: UiDocument
    live: Mapping[NodeId, LiveClass]
    classes: QtClassTable
    editors: FrozenSet[EditorKey]

@dataclass(frozen=True)
class PropertyWrite:
    owners: Tuple[NodeId, ...]
    name: str
    kind: PropKind = "property"

    def edit(self, value: Value, token: Optional[str]) -> Command:
        return self._command(value, token)

    def reset(self) -> Command:
        return self._command(None, None)

    def _command(self, value: Optional[Value], token: Optional[str]) -> Command:
        if len(self.owners) == 1:
            return SetProperty(self.owners[0], self.name, value, kind=self.kind, merge_token=token)
        return SetPropertyMany(self.owners, self.name, value, kind=self.kind, merge_token=token)

_SHORTCUT_PROPS = ("shortcut", "keySequence")
_SHORTCUT_CACHE: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, Mapping[str, str]]]" = (
    weakref.WeakKeyDictionary()
)


def form_shortcuts(document: UiDocument) -> Mapping[str, str]:
    """Shortcut text -> the object name that owns it, from this form's file only.

    Reads every widget's and action's ``shortcut`` and ``keySequence``. The
    first owner in document order wins. Cached per document revision (which
    only moves forward), so a repaint does not walk the tree again.
    """
    cached = _SHORTCUT_CACHE.get(document)
    if cached is not None and cached[0] == document.revision:
        return cached[1]
    found: Dict[str, str] = {}
    for node in document.iter_preorder():
        if isinstance(node, WidgetNode):
            owner = node.object_name
        elif isinstance(node, ActionNode):
            owner = node.name
        else:
            continue
        if not owner:
            continue
        for name in _SHORTCUT_PROPS:
            entry = node.prop(name)
            value = None if entry is None else entry.value
            if isinstance(value, (StringValue, CStringValue)) and value.text:
                found.setdefault(value.text, owner)
    view: Mapping[str, str] = MappingProxyType(found)
    _SHORTCUT_CACHE[document] = (document.revision, view)
    return view


def _bit_key(bit: str) -> Tuple[str, str]:
    parts = bit.split("::")
    if len(parts) == 1:
        return ("", parts[0])
    return (parts[0], parts[-1])

def _with_bit(current: SetValue, bit: str, on: bool) -> SetValue:
    """Return ``current`` with only ``bit`` changed. Other flags keep their spelling."""
    key = _bit_key(bit)
    pieces: List[str] = []
    for piece in current.text.split("|"):
        name = piece.strip()
        if not name or name == "0":
            continue
        if _bit_key(name) == key:
            continue
        pieces.append(name)
    if on:
        pieces.append(bit)
    if not pieces:
        return SetValue("0")
    return SetValue("|".join(pieces))

class FlagBitWrite:
    """One ``SetProperty`` per owner, changing only this flag bit."""

    def __init__(
        self,
        document: UiDocument,
        owners: Tuple[NodeId, ...],
        name: str,
        bit: str,
        defaults: Mapping[NodeId, SetValue],
    ) -> None:
        self.document = document
        self.owners = owners
        self.name = name
        self.bit = bit
        self.defaults = defaults

    def edit(self, value: Value, token: Optional[str]) -> Tuple[Command, ...]:
        if not isinstance(value, BoolValue):
            raise TypeError("a flag bit takes a BoolValue, not %s" % type(value).__name__)
        return tuple(self._set(owner, value.value, token) for owner in self.owners)

    def reset(self) -> Tuple[Command, ...]:
        return tuple(self._restore(owner) for owner in self.owners)

    def _current(self, owner: NodeId) -> SetValue:
        node = self.document.node(owner)
        if isinstance(node, (WidgetNode, LayoutNode)):
            entry = node.prop(self.name)
            if entry is not None and isinstance(entry.value, SetValue):
                return entry.value
        return self.defaults.get(owner, SetValue(""))

    def _set(self, owner: NodeId, on: bool, token: Optional[str]) -> Command:
        updated = _with_bit(self._current(owner), self.bit, on)
        return SetProperty(owner, self.name, updated, merge_token=token)

    def _restore(self, owner: NodeId) -> Command:
        default = self.defaults.get(owner, SetValue(""))
        on = _bit_key(self.bit) in default.keys()
        updated = _with_bit(self._current(owner), self.bit, on)
        if updated.keys() == default.keys():
            return SetProperty(owner, self.name, None)
        return SetProperty(owner, self.name, updated)

@dataclass(frozen=True)
class GeometryWrite:

    owner: NodeId

    def edit(self, value: Value, token: Optional[str]) -> Command:
        if not isinstance(value, RectValue):
            raise TypeError("geometry takes a RectValue, not %s" % type(value).__name__)
        return SetGeometry(self.owner, value, merge_token=token)

    def reset(self) -> Command:
        return SetProperty(self.owner, "geometry", None)

@dataclass(frozen=True)
class CellWrite:

    item: NodeId
    row: Optional[int]
    column: Optional[int]
    rowspan: Optional[int]
    colspan: Optional[int]

    def edit(self, value: Value, token: Optional[str]) -> Command:
        if not isinstance(value, SetValue):
            raise TypeError("cell alignment takes a SetValue, not %s" % type(value).__name__)
        return self._command(value.text or None)

    def reset(self) -> Command:
        return self._command(None)

    def _command(self, alignment: Optional[str]) -> Command:
        return SetLayoutCell(self.item, self.row, self.column, self.rowspan, self.colspan, alignment)

@dataclass(frozen=True)
class Crumb:
    node: NodeId
    label: str

@dataclass(frozen=True)
class OneHeader:
    node: NodeId
    name: str
    friendly: str
    qt_class: str
    glyph: str
    crumbs: Tuple[Crumb, ...]

@dataclass(frozen=True)
class ManyHeader:
    count: int
    kinds: str

HeaderView = Union[OneHeader, ManyHeader]

@dataclass(frozen=True)
class Block:

    title: str
    rows: Tuple[Row, ...]

@dataclass(frozen=True)
class GroupView:
    group: GroupId
    blocks: Tuple[Block, ...]

    def rows(self) -> Tuple[Row, ...]:
        return tuple(row for block in self.blocks for row in block.rows)

    def find(self, key: str) -> Optional[Row]:
        return next((row for row in self.rows() if row.key == key), None)

@dataclass(frozen=True)
class NodeBody:
    owners: Tuple[NodeId, ...]
    groups: Tuple[GroupView, ...]

    def group(self, group: GroupId) -> GroupView:
        return next((view for view in self.groups if view.group is group), GroupView(group, ()))

    def find(self, key: str) -> Optional[Row]:
        return next((row for view in self.groups for row in view.rows() if row.key == key), None)

@dataclass(frozen=True)
class FormBody:
    window: Optional[Row]
    design_size: str
    root_layout: str
    tab_order: Tuple[str, ...]
    problems: str
    files: str

BodyView = Union[FormBody, NodeBody]

@dataclass(frozen=True)
class ConnectionView:
    id: NodeId
    signal: str
    receiver: str
    slot: str
    words: str

@dataclass(frozen=True)
class OneBehavior:
    sender: NodeId
    sender_name: str
    connections: Tuple[ConnectionView, ...]
    empty: str
    add_signal: Optional[str]

@dataclass(frozen=True)
class ManyBehavior:
    count: int

BehaviorView = Union[OneBehavior, ManyBehavior]

@dataclass(frozen=True)
class Pages:
    body: BodyView
    behavior: BehaviorView

_NO_LIVE: Mapping[NodeId, LiveClass] = MappingProxyType({})

_WINDOW_TITLE = RowSpec(
    "windowTitle", GroupId.CONTENT, "Title", "The text in the window's title bar.", Prop("windowTitle")
)

def inspected_ids(document: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    """The nodes the inspector shows for a selection.

    A connection shows as its sender, so adding, removing or redoing one keeps
    the sender's Behavior list. Other nodes that are not widgets, layouts or
    spacers (the ``<ui>`` node, actions, items) have no inspector page of
    their own and fall back to the form.
    """
    found: List[NodeId] = []
    for node_id in ids:
        node = document.node(node_id)
        if isinstance(node, ConnectionNode):
            senders = [
                candidate
                for candidate in document.by_name(node.sender)
                if isinstance(document.node(candidate), WidgetNode)
            ]
            if not senders:
                continue
            node_id = senders[0]
        elif not isinstance(node, (WidgetNode, LayoutNode, SpacerNode)):
            continue
        if node_id not in found:
            found.append(node_id)
    return tuple(found)

def project_header(session: FormSession) -> HeaderView:
    document = session.document
    ids = inspected_ids(document, session.selection.state.ids)
    if len(ids) > 1:
        return ManyHeader(len(ids), _kinds(document, ids))
    if not ids:
        node: Node = document.root
        crumbs: Tuple[Crumb, ...] = ()
    else:
        node = document.node(ids[0])
        crumbs = _crumbs(document, node)
    name, qt_class = _name_and_class(node)
    words = class_words(qt_class)
    return OneHeader(node.id, name, words.friendly, qt_class, words.glyph, crumbs)

def project(
    session: FormSession,
    catalog: Catalog,
    *,
    search: str = "",
    live: Mapping[NodeId, LiveClass] = _NO_LIVE,
    tab_order: Optional[Callable[[], Tuple[str, ...]]] = None,
    include_all: bool = True,
    live_size: Optional[Tuple[int, int]] = None,
    sort_properties: bool = False,
) -> Pages:
    document = session.document
    owners = inspected_ids(document, session.selection.state.ids)
    facts = Facts(document, live, QtClassTable.shared(), catalog.editor_keys())
    if not owners:
        return Pages(
            _form_body(session, facts, tab_order, live_size),
            _behavior(facts, (document.root.id,)),
        )
    return Pages(
        _node_body(facts, catalog, owners, search, include_all=include_all, sort_properties=sort_properties),
        _behavior(facts, owners),
    )

def bind(facts: Facts, spec: RowSpec, owners: Tuple[NodeId, ...], *, curated: bool = True) -> Optional[Row]:
    source = spec.source
    if isinstance(source, Note):
        return LockedRow(spec.key, spec.label, "", spec.help, Unset(), source.text)
    if isinstance(source, FlagBit):
        return _flag_bit(facts, spec, owners, source)
    if isinstance(source, Prop):
        return read_property(facts, spec, owners, source.name, source.kind, curated=curated)
    if isinstance(source, LayoutProp):
        layouts = [_own_layout(facts.document, owner) for owner in owners]
        ids = tuple(layout.id for layout in layouts if layout is not None)
        if len(ids) != len(owners):
            return None
        return read_property(facts, spec, ids, source.name, "property", curated=curated)
    return _cell_alignment(facts, spec, owners)

def read_property(
    facts: Facts,
    spec: RowSpec,
    owners: Tuple[NodeId, ...],
    name: str,
    kind: PropKind,
    *,
    curated: bool,
    origin: str = "",
) -> Optional[Row]:
    nodes = [facts.document.node(owner) for owner in owners]
    entries = [_entry(node, name, kind) for node in nodes]
    lives = [_live_property(facts, owner, name, kind) for owner in owners]
    infos = [_table_property(facts, node, name, kind) for node in nodes]
    if any(entry is None and live is None and info is None for entry, live, info in zip(entries, lives, infos)):
        return None
    value = _row_value(entries, infos, lives)
    write: RowWrite = PropertyWrite(owners, name, kind)
    if kind == "property" and name in LAYOUT_OWNED:
        if any(facts.document.containing_layout_item(owner) is not None for owner in owners):
            return None if curated else _locked(spec, name, value, SET_BY_LAYOUT)
        if len(owners) != 1:
            return _locked(spec, name, value, SELECT_ONE_FOR_POSITION)
        write = GeometryWrite(next(iter(owners)))
    element, enum = _element(entries, lives, infos)
    dynamic = any(entry is not None and entry.is_dynamic for entry in entries)
    chosen = tuple(spec.choices(facts.document, owners)) if spec.choices is not None else ()
    if spec.editor:
        key = EditorKey(spec.editor)
    elif chosen:
        key = EditorKey("enum")
    else:
        key = editor_key(name, element)
    return _open_or_kept(
        facts, spec, name, value, ValueSpec(element, enum, chosen), key, write,
        origin=origin, dynamic=dynamic and kind == "property",
    )

def filter_rows(rows: Sequence[Row], search: str) -> Tuple[Row, ...]:
    needle = search.strip().lower()
    if not needle:
        return tuple(rows)
    kept: List[Row] = []
    for row in rows:
        match = _match(row, needle)
        if match is not None:
            kept.append(dataclasses.replace(row, match=match))
    return tuple(kept)

def value_text(value: RowValue) -> str:
    if isinstance(value, Written):
        return describe_value(value.value)
    if isinstance(value, Unset) and value.default is not None:
        return describe_value(value.default)
    return ""

def describe_value(value: Value) -> str:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    if isinstance(value, StringListValue):
        return ", ".join(value.items)
    if isinstance(value, BoolValue):
        return "True" if value.value else "False"
    if isinstance(value, EnumValue):
        return value.key()[1]
    if isinstance(value, SetValue):
        return ", ".join(name for _scope, name in value.keys())
    if isinstance(value, SizeValue):
        return "%d \u00d7 %d" % (value.width, value.height)
    if isinstance(value, RectValue):
        return "%d, %d, %d \u00d7 %d" % (value.x, value.y, value.width, value.height)
    if isinstance(value, PointValue):
        return "%d, %d" % (value.x, value.y)
    if isinstance(value, ColorValue):
        return "#%02X%02X%02X" % (value.red, value.green, value.blue)
    if isinstance(value, FontValue):
        parts = [value.family or "", "%d pt" % value.pointsize if value.pointsize else ""]
        return " ".join(part for part in parts if part)
    if isinstance(value, CursorShapeValue):
        return value.name
    if isinstance(value, SizePolicyValue):
        return "%s, %s" % (value.hsizetype, value.vsizetype)
    plain = getattr(value, "value", None)
    if isinstance(plain, (int, float)):
        return str(plain)
    return value.ELEMENT

class EscAction(Enum):
    CLEAR_SEARCH = "clear_search"
    REVERT_FIELD = "revert_field"
    LEAVE = "leave"

def esc_action(search: str, field_invalid: bool, field_dirty: bool = False) -> EscAction:
    """One Esc closes the innermost thing: an edit in progress, then the search."""
    if field_invalid or field_dirty:
        return EscAction.REVERT_FIELD
    if search:
        return EscAction.CLEAR_SEARCH
    return EscAction.LEAVE

_LEAVES_TAB_ORDER = (PropertyChanged,)


def tab_order_stale(changeset: ChangeSet) -> bool:
    return any(not isinstance(change, _LEAVES_TAB_ORDER) for change in changeset.changes)

def files_line(scope: FormScope) -> str:
    ui_name = os.path.basename(scope.ui_path)
    if not scope.generates or scope.generated_path is None:
        return "Saves %s." % ui_name
    folder = os.path.dirname(scope.ui_path)
    if scope.project_root:
        folder = os.path.relpath(folder, scope.project_root).replace(os.sep, "/")
    where = "the project folder" if folder == "." else folder + "/"
    return "Saves %s and %s in %s." % (ui_name, os.path.basename(scope.generated_path), where)

def problems_line(count: int) -> str:
    if count == 0:
        return "No problems."
    return "1 problem." if count == 1 else "%d problems." % count

def _node_body(
    facts: Facts,
    catalog: Catalog,
    owners: Tuple[NodeId, ...],
    search: str,
    *,
    include_all: bool = True,
    sort_properties: bool = False,
) -> NodeBody:
    curated: Dict[GroupId, List[Row]] = {}
    for spec in catalog.rows():
        if spec.classes and not all(_admits(facts, owner, spec.classes) for owner in owners):
            continue
        if spec.parent_classes and not all(_parent_admits(facts, owner, spec.parent_classes) for owner in owners):
            continue
        if spec.exclude_classes and any(_admits(facts, owner, spec.exclude_classes) for owner in owners):
            continue
        if spec.visible is not None and not spec.visible(facts.document, owners):
            continue
        row = bind(facts, spec, owners)
        if row is not None:
            curated.setdefault(spec.group, []).append(row)
    groups: List[GroupView] = []
    for group in GROUP_ORDER:
        if group is GroupId.ALL and not include_all:
            groups.append(GroupView(group, ()))
            continue
        if group is GroupId.ALL:
            blocks = _all_blocks(facts, owners, sort=sort_properties)
        else:
            blocks = (Block("", tuple(curated.get(group, ()))),)
        kept = tuple(Block(block.title, filter_rows(block.rows, search)) for block in blocks)
        kept = tuple(block for block in kept if block.rows)
        shown_body = not search and (
            (group is GroupId.LAYOUT and _layout_body(facts, catalog, owners))
            or catalog.body_applies(group, facts.document, owners)
        )
        if kept or shown_body:
            groups.append(GroupView(group, kept))
    return NodeBody(owners, tuple(groups))

def _own_layout(document: UiDocument, owner: NodeId) -> Optional[LayoutNode]:
    node = document.node(owner)
    return node if isinstance(node, LayoutNode) else document.layout_of(owner)

def _layout_body(facts: Facts, catalog: Catalog, owners: Tuple[NodeId, ...]) -> bool:
    """A bare container still gets the Layout group, so its body can offer a layout."""
    return catalog.group_body(GroupId.LAYOUT) is not None and takes_layout(facts.document, owners)

def _all_blocks(facts: Facts, owners: Tuple[NodeId, ...], *, sort: bool = False) -> Tuple[Block, ...]:
    by_class: Dict[str, List[Row]] = {}
    listed = set()
    lives = [facts.live.get(owner) for owner in owners]
    first = lives[0]
    if first is not None and all(live is not None for live in lives):
        for prop in first.properties:
            if prop.name in _HEADER_OWNED or prop.name.startswith("cbcs"):
                continue
            if any(live is None or live.find(prop.name) is None for live in lives):
                continue
            lead = facts.document.node(owners[0])
            stored_prop = lead.prop(prop.name)
            if stored_prop is not None and stored_prop.is_dynamic:
                continue
            row = read_property(
                facts, _all_spec(prop.name, "property"), owners, prop.name, "property",
                curated=False, origin=prop.declared_by,
            )
            if row is not None:
                by_class.setdefault(prop.declared_by, []).append(row)
                listed.add(("property", prop.name))
    attributes: List[Row] = []
    stored: List[Row] = []
    custom: List[Row] = []
    lead = facts.document.node(owners[0])
    for entry in lead.properties() + lead.attributes():
        kind: PropKind = "attribute" if entry.kind == "attribute" else "property"
        if (kind, entry.name) in listed or entry.name in _HEADER_OWNED or entry.name.startswith("cbcs"):
            continue
        row = read_property(
            facts, _all_spec(entry.name, kind), owners, entry.name, kind, curated=False,
        )
        if row is None:
            continue
        if kind == "property" and entry.is_dynamic:
            if isinstance(row, OpenRow):
                row = dataclasses.replace(row, dynamic=True)
            custom.append(row)
        elif kind == "attribute":
            attributes.append(row)
        else:
            stored.append(row)
    if sort:
        flat: List[Row] = []
        for rows in by_class.values():
            flat.extend(rows)
        flat.extend(attributes)
        flat.extend(stored)
        flat.extend(custom)
        flat.sort(key=lambda item: item.qt_name.lower())
        return (Block("", tuple(flat)),) if flat else ()
    blocks = [Block(title, tuple(rows)) for title, rows in by_class.items()]
    if attributes:
        blocks.append(Block("Stored by the parent", tuple(attributes)))
    if stored:
        blocks.append(Block("In the file", tuple(stored)))
    if custom:
        blocks.append(Block("Custom properties", tuple(custom)))
    return tuple(blocks)

def _all_spec(name: str, kind: PropKind) -> RowSpec:
    key = name if kind == "property" else "attribute." + name
    return RowSpec(key, GroupId.ALL, name, "", Prop(name, kind))

def _cell_alignment(facts: Facts, spec: RowSpec, owners: Tuple[NodeId, ...]) -> Optional[Row]:
    if len(owners) != 1:
        return None
    item_id = facts.document.containing_layout_item(owners[0])
    if item_id is None:
        return None
    item = facts.document.node(item_id)
    if not isinstance(item, LayoutItemNode):
        return None
    value: RowValue = Written(SetValue(item.alignment)) if item.alignment else Unset()
    write = CellWrite(item_id, item.row, item.column, item.rowspan, item.colspan)
    return _open_or_kept(facts, spec, "alignment", value, ValueSpec(SetValue.ELEMENT), ALIGNMENT, write)

def _open_or_kept(
    facts: Facts,
    spec: RowSpec,
    qt_name: str,
    value: RowValue,
    value_spec: ValueSpec,
    key: EditorKey,
    write: RowWrite,
    *,
    origin: str = "",
    dynamic: bool = False,
) -> Row:
    if spec.editor:
        key = EditorKey(spec.editor)
    if key not in facts.editors:
        return _locked(spec, qt_name, value, KEPT_AS_IS, origin)
    return OpenRow(
        spec.key, spec.label, qt_name, spec.help, value, value_spec, key, write, origin, dynamic,
    )

def _flag_bit(facts: Facts, spec: RowSpec, owners: Tuple[NodeId, ...], source: FlagBit) -> Optional[Row]:
    """Read one flag bit. Owners that disagree are Mixed. A bit at its default is Unset."""
    if not owners:
        return None
    nodes = []
    for owner in owners:
        node = facts.document.node(owner)
        if not isinstance(node, (WidgetNode, LayoutNode)):
            return None
        nodes.append(node)
    key = _bit_key(source.bit)
    states: List[bool] = []
    differs = False
    defaults: Dict[NodeId, SetValue] = {}
    for owner, node in zip(owners, nodes):
        current, default = _owner_flag(facts, node, source.name)
        defaults[owner] = default
        on = key in current.keys()
        states.append(on)
        if on != (key in default.keys()):
            differs = True
    if len(set(states)) > 1:
        value: RowValue = Mixed()
    elif differs:
        value = Written(BoolValue(states[0]))
    else:
        value = Unset(BoolValue(states[0]))
    write = FlagBitWrite(facts.document, owners, source.name, source.bit, defaults)
    editor = EditorKey(spec.editor) if spec.editor else EditorKey("bool")
    return _open_or_kept(facts, spec, source.name, value, ValueSpec(BoolValue.ELEMENT), editor, write)

def _owner_flag(facts: Facts, node: Node, name: str) -> Tuple[SetValue, SetValue]:
    info = _table_property(facts, node, name, "property")
    default = info.default if info is not None and isinstance(info.default, SetValue) else SetValue("")
    entry = node.prop(name)
    if entry is not None and isinstance(entry.value, SetValue):
        return entry.value, default
    return default, default

def _locked(spec: RowSpec, qt_name: str, value: RowValue, reason: str, origin: str = "") -> LockedRow:
    return LockedRow(spec.key, spec.label, qt_name, spec.help, value, reason, origin)

def _entry(node: Node, name: str, kind: PropKind) -> Optional[PropertyEntry]:
    return node.prop(name) if kind == "property" else node.attr(name)

def _live_property(facts: Facts, owner: NodeId, name: str, kind: PropKind) -> Optional[LiveProperty]:
    live = facts.live.get(owner)
    if live is None or kind != "property":
        return None
    return live.find(name)

def _table_property(facts: Facts, node: Node, name: str, kind: PropKind) -> Optional[PropertyInfo]:
    if kind != "property" or not isinstance(node, (WidgetNode, LayoutNode)):
        return None
    class_name = "QFrame" if node.class_name == "Line" else node.class_name
    return facts.classes.property_info(class_name, name)

def _row_value(
    entries: Sequence[Optional[PropertyEntry]],
    infos: Sequence[Optional[PropertyInfo]],
    lives: Sequence[Optional[LiveProperty]] = (),
) -> RowValue:
    present = [entry.value for entry in entries if entry is not None]
    if not present:
        live_default = _agreed_live(lives)
        if live_default is not None:
            return Unset(live_default)
        return Unset(_default(infos))
    if len(present) == len(entries) and all(semantic_equal(present[0], other) for other in present[1:]):
        return Written(present[0])
    return Mixed()

def _agreed_live(lives: Sequence[Optional[LiveProperty]]) -> Optional[Value]:
    if not lives:
        return None
    values: List[Value] = []
    for live in lives:
        if live is None or live.value is None:
            return None
        values.append(live.value)
    first = values[0]
    if all(semantic_equal(first, other) for other in values[1:]):
        return first
    return None

def _default(infos: Sequence[Optional[PropertyInfo]]) -> Optional[Value]:
    if not infos or any(info is None or info.volatile for info in infos):
        return None
    defaults = [info.default for info in infos if info is not None]
    first = defaults[0]
    return first if all(semantic_equal(first, other) for other in defaults[1:]) else None

def _element(
    entries: Sequence[Optional[PropertyEntry]],
    lives: Sequence[Optional[LiveProperty]],
    infos: Sequence[Optional[PropertyInfo]],
) -> Tuple[str, Optional[EnumSpec]]:
    live = next((item for item in lives if item is not None), None)
    stored = next((entry.value.ELEMENT for entry in entries if entry is not None), None)
    if stored is not None:
        return stored, live.enum if live is not None and live.element == stored else None
    if live is not None:
        return live.element, live.enum
    info = next((item for item in infos if item is not None), None)
    return (info.kind if info is not None else ""), None

def _match(row: Row, needle: str) -> Optional[Match]:
    candidates: Tuple[Tuple[MatchWhere, str], ...] = (
        ("label", row.label),
        ("qt_name", row.qt_name),
        ("value", value_text(row.value)),
    )
    for where, text in candidates:
        start = text.lower().find(needle)
        if start >= 0:
            return Match(where, start, start + len(needle))
    spec = getattr(row, "spec", None)
    enum = None if spec is None else getattr(spec, "enum", None)
    if enum is not None:
        for name in enum.names:
            friendly = _friendly_enum(name)
            if needle in name.lower() or needle in friendly:
                return Match("enum", 0, 0)
    for choice in getattr(spec, "choices", ()) or ():
        if needle in choice.label.lower():
            return Match("enum", 0, 0)
    return None


def _friendly_enum(name: str) -> str:
    """``NoEcho`` -> ``no echo``. Search matches these words as well as the Qt name."""
    chars: List[str] = []
    for index, ch in enumerate(name):
        if index and ch.isupper() and not name[index - 1].isupper():
            chars.append(" ")
        chars.append(ch)
    return "".join(chars).lower()

def _admits(facts: Facts, owner: NodeId, classes: Tuple[str, ...]) -> bool:
    chain = _chain(facts, owner)
    return any(name in chain for name in classes)

def _parent_admits(facts: Facts, owner: NodeId, classes: Tuple[str, ...]) -> bool:
    """The nearest ancestor that is a widget (layouts are skipped) admits one of ``classes``."""
    for ancestor in facts.document.ancestors(owner):
        if isinstance(facts.document.node(ancestor), WidgetNode):
            return _admits(facts, ancestor, classes)
    return False

def _chain(facts: Facts, owner: NodeId) -> Tuple[str, ...]:
    _name, qt_class = _name_and_class(facts.document.node(owner))
    live = facts.live.get(owner)
    if qt_class == "Line":
        # Designer stores a line as class ``Line``. Its properties are a QFrame's.
        base = live.chain if live is not None else tuple(info.name for info in facts.classes.chain("QFrame"))
        if "Line" in base:
            return base
        return ("Line",) + tuple(base)
    if live is not None:
        return live.chain
    return tuple(info.name for info in facts.classes.chain(qt_class)) or (qt_class,)

def _name_and_class(node: Node) -> Tuple[str, str]:
    if isinstance(node, (WidgetNode, LayoutNode)):
        return node.object_name, node.class_name
    if isinstance(node, SpacerNode):
        return node.name, "Spacer"
    return node.kind, node.kind

def _crumbs(document: UiDocument, node: Node) -> Tuple[Crumb, ...]:
    found: List[Crumb] = []
    for ancestor_id in reversed(document.ancestors(node.id)):
        ancestor = document.node(ancestor_id)
        if isinstance(ancestor, (WidgetNode, LayoutNode)):
            found.append(Crumb(ancestor_id, _crumb_label(ancestor)))
    found.append(Crumb(node.id, _crumb_label(node)))
    return tuple(found)

def _crumb_label(node: Node) -> str:
    name, qt_class = _name_and_class(node)
    if isinstance(node, LayoutNode):
        return class_words(qt_class).friendly.lower()
    return name or class_words(qt_class).friendly

def _kinds(document: UiDocument, ids: Sequence[NodeId]) -> str:
    counts = Counter(_name_and_class(document.node(node_id))[1] for node_id in ids)
    parts = []
    for qt_class, count in counts.items():
        words = class_words(qt_class)
        parts.append("%d %s" % (count, words.plural if count > 1 else words.friendly.lower()))
    return ", ".join(parts)

def _form_body(
    session: FormSession,
    facts: Facts,
    tab_order: Optional[Callable[[], Tuple[str, ...]]],
    live_size: Optional[Tuple[int, int]] = None,
) -> FormBody:
    document = session.document
    root = document.root
    geometry = root.value("geometry")
    layout = root.layout
    if isinstance(geometry, RectValue):
        design_size = "%d \u00d7 %d px" % (geometry.width, geometry.height)
    elif live_size is not None:
        design_size = "%d \u00d7 %d px" % (live_size[0], live_size[1])
    else:
        design_size = NOT_SET
    return FormBody(
        window=bind(facts, _WINDOW_TITLE, (root.id,)),
        design_size=design_size,
        root_layout=class_words(layout.class_name).friendly if layout is not None else "No layout",
        tab_order=tab_order() if tab_order is not None else effective_tab_order(document),
        problems=problems_line(len(session.diagnostics.all())),
        files=files_line(session.scope),
    )

def _behavior(facts: Facts, owners: Tuple[NodeId, ...]) -> BehaviorView:
    if len(owners) != 1:
        return ManyBehavior(len(owners))
    node = facts.document.node(owners[0])
    name, qt_class = _name_and_class(node)
    connections = tuple(
        _connection_view(connection)
        for connection in facts.document.connections()
        if isinstance(connection, ConnectionNode) and name and connection.sender == name
    )
    signal = default_signal(_chain(facts, node.id), facts.classes)
    noun = class_words(qt_class).noun
    if signal is None:
        empty = "Nothing happens yet with this %s." % noun
    else:
        empty = "Nothing happens yet when %s." % event_words(signal).clause.format(noun=noun)
    return OneBehavior(node.id, name, connections, empty, signal)

def _connection_view(connection: ConnectionNode) -> ConnectionView:
    words = "When %s \u2192 %s \u00b7 %s" % (
        event_words(connection.signal).short,
        connection.receiver,
        connection.slot,
    )
    return ConnectionView(connection.id, connection.signal, connection.receiver, connection.slot, words)
