"""Copy a selection into a fragment and choose where a paste lands.

The clipboard itself is not an engine object. Callers turn the fragment into
XML. This module stays on the document and the placement types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.commands.placement import (
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
    Placement,
)
from app.features.form_builder.engine.commands.refs import NAME_FIELD
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import (
    form_item_role,
    form_rows,
    grid_shape,
    is_container,
    is_page_container,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    Node,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.schema import SCHEMA
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import CStringValue, NumberValue, RectValue, StringValue

_COPYABLE = frozenset({"widget", "layout", "spacer", "action", "actiongroup", "buttongroup"})
_PAGE_HOSTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})
_GRID = "QGridLayout"
_FORM = "QFormLayout"
_OFFSET = 16
_GAP = 8
_DEFAULT_SIZE = (80, 24)
_MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")


@dataclass(frozen=True)
class CopiedBox:
    """The size of one copied top-level piece, and where it sat when that is known.

    ``x`` and ``y`` share one frame across a paste (the source form), so they
    only matter relative to each other.
    """

    width: int
    height: int
    x: Optional[int] = None
    y: Optional[int] = None


#: Measures a copied spec that carries no geometry. None when it cannot.
Measure = Callable[[NodeSpec], Optional[CopiedBox]]


def selection_fragment(doc: UiDocument, ids: Sequence[NodeId]) -> Fragment:
    """Selected subtrees, buddies among them, and connections that touch them.

    A selected descendant of another selected node is not copied twice.
    Selecting the form copies its contents, never the root widget.
    Ids are cleared. A buddy that names something outside the copied set is
    left out. A connection with both ends in the set is copied. A connection
    with one end outside is copied too, so paste can keep it only when that
    end is missing on the target.
    """
    roots = _copy_roots(doc, ids)
    specs = tuple(_without_ids(doc.node(node_id).to_spec()) for node_id in roots)
    names = set(_listed_names(specs))
    specs = tuple(_without_outside_buddies(spec, names) for spec in specs)
    connections = [
        _without_ids(node.to_spec())
        for node in doc.connections()
        if _touches_selection(node, names)
    ]
    return Fragment(
        nodes=specs,
        connections=tuple(connections),
        customwidgets=_custom_widgets(doc, specs),
    )


def fragment_source_ids(doc: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    """Document nodes ``selection_fragment`` copies, in that same order."""
    return _copy_roots(doc, ids)


def paste_placement(doc: UiDocument, anchor_ids: Sequence[NodeId]) -> Placement:
    """Where a paste goes for the current selection (UX-CLIP-002).

    ``anchor_ids`` is the selection. The last id that is still in the document
    wins. An empty selection uses the form root. A label and its field cannot
    share one placement, so two copied form widgets become two inserted rows.
    """
    anchor = _anchor(doc, anchor_ids)
    if anchor is None:
        return _place_widget(doc, doc.root)
    node = doc.node(anchor)
    if isinstance(node, LayoutNode):
        return _end_of_layout(doc, node)
    if isinstance(node, WidgetNode):
        return _place_widget(doc, node)
    item = _holding_item(doc, node.id)
    if item is not None:
        return _after_item(doc, item)
    return _place_widget(doc, doc.root)


def plain_names(fragment: Fragment) -> str:
    """One object name per line, document order. Empty when nothing is named."""
    return "\n".join(_listed_names(fragment.nodes))


def paste_anchor_name(doc: UiDocument, anchor_ids: Sequence[NodeId]) -> str:
    """What a paste was placed after: visible text, then the object name (UX-COPY-003).

    The form root reads as ``the form``. A layout has no text of its own.
    """
    anchor = _anchor(doc, anchor_ids)
    if anchor is None or anchor == doc.root.id:
        return "the form"
    node = doc.node(anchor)
    if isinstance(node, WidgetNode):
        return _shown_name(doc, anchor)
    if isinstance(node, LayoutNode) and node.object_name:
        return node.object_name
    return "the form"


def plan_paste(
    doc: UiDocument,
    anchor_ids: Sequence[NodeId],
    fragment: Fragment,
    measure: Optional[Measure] = None,
) -> Tuple[Placement, Fragment, bool]:
    """Placement, fragment, and ``auto_layout`` for one ``InsertFragment`` paste."""
    placement = paste_placement(doc, anchor_ids)
    auto_layout = paste_auto_layout(placement)
    if isinstance(placement, InContainer) and placement.geometry is not None:
        placement, fragment = free_paste(doc, placement, fragment, measure)
    return placement, fragment, auto_layout


def free_paste(
    doc: UiDocument,
    placement: InContainer,
    fragment: Fragment,
    measure: Optional[Measure] = None,
) -> Tuple[InContainer, Fragment]:
    """Give every top-level piece of a paste into a free container its own rectangle.

    ``placement`` is a free spot from ``paste_placement``; its corner is where
    the paste would like to start. Each piece keeps its copied size. A piece
    with no geometry (it came out of a layout) takes ``measure``'s size, else
    a default. The pieces keep their arrangement as one group, the group goes
    to the free spot nearest that corner, and it stays inside the container.
    A layout or spacer is wrapped in a ``widget`` first, as Designer does.

    Returns a placement with no geometry and the fragment with geometry set.
    """
    boxes: List[CopiedBox] = []
    for spec in fragment.nodes:
        rect = _spec_rect(spec)
        if rect is not None:
            boxes.append(CopiedBox(rect.width, rect.height, rect.x, rect.y))
            continue
        found = measure(spec) if measure is not None else None
        if found is None or found.width <= 0 or found.height <= 0:
            width, height = _DEFAULT_SIZE
            found = CopiedBox(width, height)
        boxes.append(found)
    offsets = _arrange(boxes)
    group_w = max((box.x + box.width for box in offsets), default=0)
    group_h = max((box.y + box.height for box in offsets), default=0)
    container = doc.node(placement.widget)
    taken: List[RectValue] = []
    bounds: Optional[Tuple[int, int]] = None
    if isinstance(container, WidgetNode):
        taken = [rect for rect in (_node_rect(child) for child in container.child_widgets) if rect is not None]
        own = _node_rect(container)
        if own is not None and own.width > 0 and own.height > 0:
            bounds = (own.width, own.height)
    want = placement.geometry
    prefer = (want.x, want.y) if want is not None else (_OFFSET, _OFFSET)
    left, top = _free_spot(prefer, (group_w, group_h), taken, bounds)
    nodes = tuple(
        _with_geometry(free_holder(spec), RectValue(left + box.x, top + box.y, box.width, box.height))
        for spec, box in zip(fragment.nodes, offsets)
    )
    placed = Fragment(
        nodes=nodes,
        connections=fragment.connections,
        customwidgets=fragment.customwidgets,
        resources=fragment.resources,
    )
    return InContainer(placement.widget, placement.index), placed


def paste_auto_layout(placement: Placement) -> bool:
    """A free widget already carries geometry, so paste must not add a box."""
    if isinstance(placement, InContainer) and placement.geometry is not None:
        return False
    return True


def selectable_ids(doc: UiDocument) -> Tuple[NodeId, ...]:
    """Every widget and layout, including the root. The document node stays out."""
    return tuple(node.id for node in doc.iter_preorder() if node.kind in ("widget", "layout"))


def pasted_widget_count(fragment: Fragment) -> int:
    """Widgets in ``fragment``. A fragment with none counts its top-level nodes.

    A page of a tab, stack, or toolbox is not a widget in this count. A widget
    on that page is.
    """
    count = sum(_widget_count(spec) for spec in fragment.nodes)
    return count or len(fragment.nodes)


def paste_status(count: int, anchor: str) -> str:
    """Status sentence for a paste. One widget does not take a plural noun."""
    return "Pasted %d %s after %s" % (count, _noun(count, "widget", "widgets"), anchor)


def paste_sentence(doc: UiDocument, anchor_ids: Sequence[NodeId], count: int) -> str:
    """Status sentence. A container is named by its visible text, never by a layout name."""
    noun = _noun(count, "widget", "widgets")
    placement = paste_placement(doc, anchor_ids)
    if isinstance(placement, InContainer):
        return "Pasted %d %s into %s" % (count, noun, _shown_name(doc, placement.widget))
    anchor = _anchor(doc, anchor_ids)
    node = doc.get(anchor) if anchor is not None else None
    if isinstance(node, LayoutNode):
        owner = node.owner_widget_id()
        if owner is not None:
            return "Pasted %d %s into %s" % (count, noun, _shown_name(doc, owner))
    if isinstance(node, WidgetNode) and node.layout is not None:
        return "Pasted %d %s into %s" % (count, noun, _shown_name(doc, node.id))
    return paste_status(count, paste_anchor_name(doc, anchor_ids))


def duplicate_sentence(doc: UiDocument, anchor_ids: Sequence[NodeId]) -> str:
    """One sentence for duplicate. The name is the visible text, then the object name."""
    anchor = _anchor(doc, anchor_ids)
    if anchor is None or not doc.contains(anchor) or anchor == doc.root.id:
        return "Duplicated the selection."
    return "Duplicated %s." % _shown_name(doc, anchor)


def cut_sentence(count: int) -> str:
    """One sentence for cut."""
    return "Cut %d %s." % (count, _noun(count, "widget", "widgets"))


def connections_for_paste(fragment: Fragment, target_names: AbstractSet[str]) -> Tuple[NodeSpec, ...]:
    """Connections paste may insert.

    Both ends in the copied set stay. One end outside stays only when that
    name is not already a widget on the target. An outside name that exists
    is dropped so paste never wires a widget the user did not copy.
    """
    copied = set(_listed_names(fragment.nodes))
    kept: List[NodeSpec] = []
    for spec in fragment.connections:
        outside: List[str] = []
        for key in ("sender", "receiver"):
            value = spec.field(key)
            if isinstance(value, str) and value and value not in copied:
                outside.append(value)
        if outside and all(name in target_names for name in outside):
            continue
        kept.append(spec)
    return tuple(kept)


def sibling_ids(doc: UiDocument, current: Optional[NodeId], ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    """Every sibling of the anchor, in document order. The form selects its contents."""
    anchor = current if current is not None and doc.contains(current) else None
    if anchor is None:
        for node_id in ids:
            if doc.contains(node_id):
                anchor = node_id
                break
    if anchor is None:
        return ()
    node = doc.node(anchor)
    if anchor == doc.root.id and isinstance(node, WidgetNode):
        return _content_ids(doc, node)
    parent = doc.parent(anchor)
    if isinstance(parent, LayoutItemNode):
        layout = doc.parent(parent.id)
        if isinstance(layout, LayoutNode):
            return _item_contents(layout)
    if isinstance(parent, WidgetNode):
        return tuple(child.id for child in parent.child_widgets)
    return (anchor,)


def command_enabled(
    doc: UiDocument,
    ids: Sequence[NodeId],
    command_id: str,
    has_fragment: bool,
) -> bool:
    """Whether a clipboard command can act on this selection and clipboard."""
    if command_id == "form.action.paste":
        return has_fragment
    if command_id in ("form.action.copy", "form.action.duplicate", "form.action.savePiece"):
        return bool(selection_fragment(doc, ids).nodes)
    if command_id in ("form.action.cut", "form.action.delete", "form.action.backspace"):
        root = doc.root.id
        ui = doc.ui.id
        return any(node_id not in (root, ui) and doc.contains(node_id) for node_id in ids)
    if command_id in ("form.action.selectAll", "form.action.selectAllSiblings"):
        return True
    return False


def dangling_sentence(
    fragment: Fragment,
    dangling: Sequence[str],
    renames: Sequence[Tuple[str, str]],
    alive: AbstractSet[str],
) -> Optional[str]:
    """The toast when a paste kept a connection that names a missing widget."""
    if not dangling:
        return None
    count = pasted_widget_count(fragment)
    gaps = missing_connection_count(fragment, renames, alive)
    if gaps < 1:
        gaps = len(dangling)
    widgets = "%d %s" % (count, _noun(count, "widget", "widgets"))
    links = "%d %s" % (gaps, _noun(gaps, "connection", "connections"))
    verb = "points" if gaps == 1 else "point"
    return "Pasted %s. %s %s at a widget that isn't on this form." % (widgets, links, verb)


def _noun(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def missing_connection_count(
    fragment: Fragment,
    renames: Sequence[Tuple[str, str]],
    alive: AbstractSet[str],
) -> int:
    """Connections whose sender or receiver is not a name on the form."""
    mapping = dict(renames)
    found = 0
    for spec in fragment.connections:
        if _end_missing(spec, mapping, alive):
            found += 1
    return found


def _widget_count(spec: NodeSpec) -> int:
    return _count_widgets(spec, False)


def _count_widgets(spec: NodeSpec, page: bool) -> int:
    count = 0 if page or spec.kind != "widget" else 1
    host = spec.kind == "widget" and spec.field("class_name") in _PAGE_HOSTS
    for slot, kids in spec.slots:
        for child in kids:
            child_page = bool(host and slot == "children" and child.kind == "widget")
            count += _count_widgets(child, child_page)
    return count


def _end_missing(spec: NodeSpec, mapping: Dict[str, str], alive: AbstractSet[str]) -> bool:
    for key in ("sender", "receiver"):
        value = spec.field(key)
        if not isinstance(value, str) or not value:
            continue
        value = mapping.get(value, value)
        if value not in alive:
            return True
    return False


def _copy_roots(doc: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    chosen: List[NodeId] = []
    seen: Set[NodeId] = set()
    for node_id in ids:
        if node_id in seen or not doc.contains(node_id):
            continue
        seen.add(node_id)
        target = _copy_target(doc, node_id)
        if target is None:
            continue
        chosen.append(target.id)
    chosen_set = set(chosen)
    roots = [
        node_id
        for node_id in chosen
        if not any(doc.is_ancestor(other, node_id) for other in chosen_set if other != node_id)
    ]
    order = {node.id: index for index, node in enumerate(doc.iter_preorder())}
    unique: List[NodeId] = []
    taken: Set[NodeId] = set()
    for node_id in sorted(roots, key=lambda item: order.get(item, 0)):
        if node_id in taken:
            continue
        taken.add(node_id)
        unique.append(node_id)
    expanded: List[NodeId] = []
    for node_id in unique:
        node = doc.node(node_id)
        if node_id == doc.root.id and isinstance(node, WidgetNode):
            expanded.extend(_content_ids(doc, node))
        else:
            expanded.append(node_id)
    return _dedupe_roots(doc, expanded)


def _dedupe_roots(doc: UiDocument, node_ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    chosen = [node_id for node_id in node_ids if doc.contains(node_id)]
    chosen_set = set(chosen)
    roots = [
        node_id
        for node_id in chosen
        if not any(doc.is_ancestor(other, node_id) for other in chosen_set if other != node_id)
    ]
    order = {node.id: index for index, node in enumerate(doc.iter_preorder())}
    unique: List[NodeId] = []
    taken: Set[NodeId] = set()
    for node_id in sorted(roots, key=lambda item: order.get(item, 0)):
        if node_id in taken:
            continue
        taken.add(node_id)
        unique.append(node_id)
    return tuple(unique)


def _content_ids(doc: UiDocument, widget: WidgetNode) -> Tuple[NodeId, ...]:
    """What copying the form copies: the root layout's items, or the free children."""
    if widget.layout is not None:
        return _item_contents(widget.layout)
    return tuple(child.id for child in widget.child_widgets)


def _item_contents(layout: LayoutNode) -> Tuple[NodeId, ...]:
    found: List[NodeId] = []
    for item in layout.items:
        content = item.content
        if content is not None and content.kind in _COPYABLE:
            found.append(content.id)
    return tuple(found)


def _shown_name(doc: UiDocument, node_id: NodeId) -> str:
    """Visible text, then the object name. Layouts borrow the widget that owns them."""
    node = doc.get(node_id)
    if isinstance(node, LayoutNode):
        owner = node.owner_widget_id()
        if owner is not None:
            return _shown_name(doc, owner)
        return "the form"
    if isinstance(node, WidgetNode):
        for key in ("text", "title", "windowTitle"):
            value = node.value(key)
            if isinstance(value, (StringValue, CStringValue)) and value.text.strip():
                return value.text.strip()
        if node.object_name:
            return node.object_name
    return "the form"


def _copy_target(doc: UiDocument, node_id: NodeId) -> Optional[Node]:
    node = doc.get(node_id)
    if node is None or node.kind == "ui":
        return None
    if isinstance(node, LayoutItemNode):
        content = node.content
        if content is None or content.kind not in _COPYABLE:
            return None
        return content
    if node.kind not in _COPYABLE:
        return None
    return node


def _touches_selection(node: Node, names: Set[str]) -> bool:
    sender = node.field("sender")
    receiver = node.field("receiver")
    if not isinstance(sender, str) or not isinstance(receiver, str):
        return False
    return sender in names or receiver in names


def _custom_widgets(doc: UiDocument, specs: Sequence[NodeSpec]) -> Tuple[NodeSpec, ...]:
    used = _class_names(specs)
    found = []
    for node in doc.ui.children("customwidgets"):
        class_name = node.field("class_name")
        if isinstance(class_name, str) and class_name in used:
            found.append(_without_ids(node.to_spec()))
    return tuple(found)


def _class_names(specs: Sequence[NodeSpec]) -> Set[str]:
    found: Set[str] = set()

    def walk(spec: NodeSpec) -> None:
        if spec.kind == "widget":
            class_name = spec.field("class_name")
            if isinstance(class_name, str) and class_name:
                found.add(class_name)
        for _slot, kids in spec.slots:
            for child in kids:
                walk(child)

    for spec in specs:
        walk(spec)
    return found


def _listed_names(specs: Sequence[NodeSpec]) -> Tuple[str, ...]:
    found: List[str] = []

    def walk(spec: NodeSpec) -> None:
        field_name = NAME_FIELD.get(spec.kind)
        if field_name is not None:
            value = spec.field(field_name)
            if isinstance(value, str) and value:
                found.append(value)
        for _slot, kids in spec.slots:
            for child in kids:
                walk(child)

    for spec in specs:
        walk(spec)
    return tuple(found)


def _without_outside_buddies(spec: NodeSpec, names: Set[str]) -> NodeSpec:
    properties = tuple(
        entry for entry in spec.properties if not _buddy_leaves(entry, names)
    )
    slots = tuple(
        (slot, tuple(_without_outside_buddies(child, names) for child in kids))
        for slot, kids in spec.slots
    )
    if properties == spec.properties and slots == spec.slots:
        return spec
    return NodeSpec(
        spec.kind,
        spec.id,
        spec.fields,
        properties,
        spec.attributes,
        slots,
        spec.extra_attrs,
    )


def _buddy_leaves(entry: PropertyEntry, names: Set[str]) -> bool:
    if entry.name != "buddy":
        return False
    value = entry.value
    if isinstance(value, (CStringValue, StringValue)):
        return value.text not in names
    return False


def _without_ids(spec: NodeSpec) -> NodeSpec:
    return NodeSpec(
        kind=spec.kind,
        id=None,
        fields=spec.fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=tuple((name, tuple(_without_ids(child) for child in kids)) for name, kids in spec.slots),
        extra_attrs=spec.extra_attrs,
    )


def _anchor(doc: UiDocument, ids: Sequence[NodeId]) -> Optional[NodeId]:
    found: Optional[NodeId] = None
    for node_id in ids:
        if doc.contains(node_id):
            found = node_id
    return found


def _place_widget(doc: UiDocument, widget: WidgetNode) -> Placement:
    if is_page_container(doc, widget.id):
        page = _current_page(widget)
        if page is None:
            return InContainer(widget.id, len(widget.child_widgets))
        return _place_widget(doc, page)
    if widget.layout is not None:
        return _end_of_layout(doc, widget.layout)
    # UX-BARE-001 makes a vertical layout only when the container is empty.
    # A container that already has free children keeps those rectangles.
    if (is_container(doc, widget.id) or widget.id == doc.root.id) and not is_page_container(doc, widget.id):
        if widget.child_widgets:
            return _beside(widget, widget.child_widgets[-1])
        return InContainer(widget.id, 0)
    item = _holding_item(doc, widget.id)
    if item is not None:
        return _after_item(doc, item)
    parent = doc.parent(widget.id)
    if (
        isinstance(parent, WidgetNode)
        and parent.layout is None
        and not is_page_container(doc, parent.id)
    ):
        return _beside(parent, widget)
    if widget.id == doc.root.id:
        return InContainer(widget.id, len(widget.child_widgets))
    return _place_widget(doc, doc.root)


def _end_of_layout(doc: UiDocument, layout: LayoutNode) -> Placement:
    """Next free place. Grid and form match ``drop_plan`` auto placement."""
    if layout.class_name == _GRID:
        shape = grid_shape(doc, layout.id)
        if shape.empty:
            row, column = shape.empty[0]
            return InGridCell(layout.id, row, column)
        return InGridCell(layout.id, shape.rows, 0)
    if layout.class_name == _FORM:
        rows = form_rows(doc, layout.id)
        if rows:
            _label, field, spanning = rows[-1]
            if spanning is None and field is None:
                return InFormRow(layout.id, len(rows) - 1, "field", False)
            if spanning is None and _label is None:
                return InFormRow(layout.id, len(rows) - 1, "label", False)
        return InFormRow(layout.id, len(rows), "field", True)
    return InBoxLayout(layout.id, len(layout.items))


def _after_item(doc: UiDocument, item: LayoutItemNode) -> Placement:
    parent = doc.parent(item.id)
    if not isinstance(parent, LayoutNode):
        return _place_widget(doc, doc.root)
    if parent.class_name == _GRID:
        return _grid_after(doc, parent, item)
    if parent.class_name == _FORM:
        row = (item.row or 0) + (item.rowspan or 1)
        role = form_item_role(item.column, item.colspan)
        return InFormRow(parent.id, row, role, True)
    return InBoxLayout(parent.id, item.slot_index + 1)


def _grid_after(doc: UiDocument, layout: LayoutNode, item: LayoutItemNode) -> InGridCell:
    row = item.row or 0
    column = item.column or 0
    rowspan = item.rowspan or 1
    anchor = (row, column)
    for cell in grid_shape(doc, layout.id).empty:
        if cell > anchor:
            return InGridCell(layout.id, cell[0], cell[1])
    return InGridCell(layout.id, row + rowspan, column, mode="insert_row")


def _beside(parent: WidgetNode, anchor: WidgetNode) -> InContainer:
    """A free spot 16, 16 px past the anchor's corner. ``free_paste`` sizes each piece."""
    rect = anchor.value("geometry")
    width, height = _DEFAULT_SIZE
    if isinstance(rect, RectValue):
        box = RectValue(rect.x + _OFFSET, rect.y + _OFFSET, width, height)
    else:
        box = RectValue(_OFFSET, _OFFSET, width, height)
    return InContainer(parent.id, len(parent.child_widgets), box)


def free_holder(spec: NodeSpec, holder_name: str = "widget", layout_name: str = "verticalLayout") -> NodeSpec:
    """Wrap a layout or spacer in a plain ``QWidget`` so it can sit at a coordinate.

    Designer names that widget ``widget`` and gives the layout zero margins,
    so it looks as it did nested in its source. A spacer first gets a
    vertical layout of its own. Any other spec comes back unchanged.
    """
    if spec.kind not in ("layout", "spacer"):
        return spec
    held = spec
    if spec.kind == "spacer":
        item = NodeSpec("layoutitem", None, (), (), (), (("content", (spec,)),))
        held = NodeSpec(
            "layout",
            None,
            _fields("layout", {"class_name": "QVBoxLayout", "object_name": layout_name}),
            (),
            (),
            (("layout_items", (item,)),),
        )
    return NodeSpec(
        "widget",
        None,
        _fields("widget", {"class_name": "QWidget", "object_name": holder_name}),
        (),
        (),
        (("layout", (_flush_margins(held),)),),
    )


def _flush_margins(layout: NodeSpec) -> NodeSpec:
    named = {entry.name for entry in layout.properties}
    if named & set(_MARGINS) or "margin" in named:
        return layout
    zero = tuple(PropertyEntry("property", name, NumberValue(0)) for name in _MARGINS)
    return NodeSpec(
        layout.kind,
        layout.id,
        layout.fields,
        zero + layout.properties,
        layout.attributes,
        layout.slots,
        layout.extra_attrs,
    )


def _fields(kind: str, values: Dict[str, object]) -> Tuple[Tuple[str, object], ...]:
    return tuple((spec.name, values[spec.name]) for spec in SCHEMA[kind].fields if values.get(spec.name) is not None)


def _spec_rect(spec: NodeSpec) -> Optional[RectValue]:
    if spec.kind != "widget":
        return None
    for entry in spec.properties:
        if entry.name == "geometry" and isinstance(entry.value, RectValue):
            return entry.value
    return None


def _node_rect(node: WidgetNode) -> Optional[RectValue]:
    rect = node.value("geometry")
    return rect if isinstance(rect, RectValue) else None


def _with_geometry(spec: NodeSpec, rect: RectValue) -> NodeSpec:
    entry = PropertyEntry("property", "geometry", rect)
    kept = [item for item in spec.properties if item.name != "geometry"]
    index = next((at for at, item in enumerate(spec.properties) if item.name == "geometry"), 0)
    kept.insert(index, entry)
    return NodeSpec(spec.kind, spec.id, spec.fields, tuple(kept), spec.attributes, spec.slots, spec.extra_attrs)


def _arrange(boxes: Sequence[CopiedBox]) -> Tuple[RectValue, ...]:
    """Offsets from the group's corner. Known spots keep their arrangement.

    Pieces with no known spot stack under the rest. If the copied spots would
    overlap (a size hint outgrew a squeezed layout cell), the whole group
    stacks as one column instead, so a paste never lands on itself.
    """
    known = [(box.x, box.y) for box in boxes if box.x is not None and box.y is not None]
    left = min((x for x, _y in known), default=0)
    top = min((y for _x, y in known), default=0)
    below = max(
        (box.y - top + box.height for box in boxes if box.x is not None and box.y is not None),
        default=0,
    )
    placed: List[RectValue] = []
    for box in boxes:
        if box.x is not None and box.y is not None:
            placed.append(RectValue(box.x - left, box.y - top, box.width, box.height))
            continue
        y = below + _GAP if below else 0
        placed.append(RectValue(0, y, box.width, box.height))
        below = y + box.height
    if not any(_meets(first, second) for index, first in enumerate(placed) for second in placed[index + 1 :]):
        return tuple(placed)
    column: List[RectValue] = []
    y = 0
    for box in boxes:
        column.append(RectValue(0, y, box.width, box.height))
        y += box.height + _GAP
    return tuple(column)


def _meets(first: RectValue, second: RectValue) -> bool:
    return (
        first.x < second.x + second.width
        and second.x < first.x + first.width
        and first.y < second.y + second.height
        and second.y < first.y + first.height
    )


def _free_spot(
    prefer: Tuple[int, int],
    size: Tuple[int, int],
    taken: Sequence[RectValue],
    bounds: Optional[Tuple[int, int]],
) -> Tuple[int, int]:
    """The corner nearest ``prefer`` where a ``size`` group covers nothing.

    Candidates line up with the preferred corner and with the edges of the
    widgets already there. With no free spot, the preferred corner is kept,
    pulled inside ``bounds``.
    """
    width, height = size
    px, py = prefer
    xs = {px, _GAP}
    ys = {py, _GAP}
    for rect in taken:
        xs.update((rect.x, rect.x + rect.width + _GAP))
        ys.update((rect.y, rect.y + rect.height + _GAP))
    best: Optional[Tuple[int, int, int]] = None
    for y in sorted(ys):
        for x in sorted(xs):
            if not _fits(x, y, width, height, bounds):
                continue
            if any(_meets(RectValue(x, y, width, height), rect) for rect in taken):
                continue
            distance = (x - px) * (x - px) + (y - py) * (y - py)
            if best is None or distance < best[0]:
                best = (distance, x, y)
    if best is not None:
        return best[1], best[2]
    return _clamp(px, width, bounds[0] if bounds else None), _clamp(py, height, bounds[1] if bounds else None)


def _fits(x: int, y: int, width: int, height: int, bounds: Optional[Tuple[int, int]]) -> bool:
    if x < 0 or y < 0:
        return False
    if bounds is None:
        return True
    return x + width <= bounds[0] and y + height <= bounds[1]


def _clamp(value: int, extent: int, limit: Optional[int]) -> int:
    if limit is not None:
        value = min(value, limit - extent)
    return max(0, value)


def _holding_item(doc: UiDocument, node_id: NodeId) -> Optional[LayoutItemNode]:
    parent = doc.parent(node_id)
    if isinstance(parent, LayoutItemNode):
        return parent
    return None


def _current_page(widget: WidgetNode) -> Optional[WidgetNode]:
    pages = widget.child_widgets
    if not pages:
        return None
    index = 0
    entry = widget.prop("currentIndex")
    if entry is not None and isinstance(entry.value, NumberValue):
        value = entry.value.value
        if isinstance(value, int) and not isinstance(value, bool):
            index = value
    if index < 0 or index >= len(pages):
        index = 0
    return pages[index]

