"""Copy a selection into a fragment and choose where a paste lands.

The clipboard itself is not an engine object. Callers turn the fragment into
XML. This module stays on the document and the placement types.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple

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
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import CStringValue, NumberValue, RectValue, StringValue

_COPYABLE = frozenset({"widget", "layout", "spacer", "action", "actiongroup", "buttongroup"})
_GRID = "QGridLayout"
_FORM = "QFormLayout"
_OFFSET = 16
_DEFAULT_SIZE = (80, 24)


def selection_fragment(doc: UiDocument, ids: Sequence[NodeId]) -> Fragment:
    """Selected subtrees, buddies among them, and connections among them.

    A selected descendant of another selected node is not copied twice.
    Ids are cleared. A buddy or connection that names something outside the
    copied set is left out.
    """
    roots = _copy_roots(doc, ids)
    specs = tuple(_without_ids(doc.node(node_id).to_spec()) for node_id in roots)
    names = set(_listed_names(specs))
    specs = tuple(_without_outside_buddies(spec, names) for spec in specs)
    connections = [
        _without_ids(node.to_spec())
        for node in doc.connections()
        if _names_a_pair(node, names)
    ]
    return Fragment(
        nodes=specs,
        connections=tuple(connections),
        customwidgets=_custom_widgets(doc, specs),
    )


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
    return tuple(unique)


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


def _names_a_pair(node: Node, names: Set[str]) -> bool:
    sender = node.field("sender")
    receiver = node.field("receiver")
    return (
        isinstance(sender, str)
        and isinstance(receiver, str)
        and sender in names
        and receiver in names
    )


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
    if is_container(doc, widget.id):
        return InContainer(widget.id, len(widget.child_widgets))
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
    rect = anchor.value("geometry")
    if isinstance(rect, RectValue):
        box = RectValue(rect.x + _OFFSET, rect.y + _OFFSET, rect.width, rect.height)
    else:
        width, height = _DEFAULT_SIZE
        box = RectValue(_OFFSET, _OFFSET, width, height)
    return InContainer(parent.id, len(parent.child_widgets), box)


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

