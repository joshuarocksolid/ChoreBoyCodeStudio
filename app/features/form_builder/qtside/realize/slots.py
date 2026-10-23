"""Layout items, reconciled by difference.

Each realized layout has a mirror: the item fields, content id and object of
every item it holds, in Qt's item order. A patch hands each dirty layout the
content ids its ChangeSet removed and the items it inserted, moved or edited
(``collect_layout_hints``). The layout takes out and puts back only those, so
moving one widget out of a 400-cell grid is one ``takeAt``. Index lookups run
on a plain list of ids, so the Python work is O(changed).

A layout without hints, or whose mirror cannot be trusted, compares every
document item with the mirror instead. That is O(items) in Python and still
touches Qt only where an item differs.

Two rules keep the Qt side safe:

* A mirror is trusted only while ``count()`` matches it. Anything that removed
  an item behind the mirror's back makes the next reconcile rebuild that one
  layout from scratch.
* A layout that leaves the live tree is emptied first. A detached layout that
  still holds items keeps pointers to widgets that later move or die, and the
  next read of such an item is a use-after-free.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

from app.qt.QtWidgets import QBoxLayout, QFormLayout, QGridLayout, QLayout, QWidget
from app.qt.qt_compat import wrapper_is_valid
from app.features.form_builder.engine.events import (
    ChangeSet,
    FieldChanged,
    NodeInserted,
    NodeMoved,
    NodeRemoved,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.qtside.realize.props import resolve_enum

logger = logging.getLogger(__name__)

NODE_ID_PROPERTY = "_cbcsNodeId"

LAYOUT_ITEM_FIELDS = frozenset({"row", "column", "rowspan", "colspan", "alignment"})

_BOX = "box"
_GRID = "grid"
_FORM = "form"

Taken = List[Tuple[Optional[NodeId], object]]


class _Mirror:
    """What one QLayout holds, in item order. ``ids`` is kept for list.index."""

    __slots__ = ("layout", "fields", "ids", "objects", "nested")

    def __init__(self, layout: QLayout) -> None:
        self.layout = layout
        self.fields: List[object] = []
        self.ids: List[NodeId] = []
        self.objects: List[object] = []
        self.nested = 0

    def __len__(self) -> int:
        return len(self.ids)

    def find(self, content_id: NodeId) -> int:
        try:
            return self.ids.index(content_id)
        except ValueError:
            return -1

    def insert(self, index: int, fields: object, content_id: NodeId, obj: object) -> None:
        self.fields.insert(index, fields)
        self.ids.insert(index, content_id)
        self.objects.insert(index, obj)
        if isinstance(obj, QLayout):
            self.nested += 1

    def remove(self, index: int) -> Tuple[NodeId, object]:
        del self.fields[index]
        obj = self.objects.pop(index)
        if isinstance(obj, QLayout):
            self.nested -= 1
        return self.ids.pop(index), obj

    def clear(self) -> None:
        del self.fields[:]
        del self.ids[:]
        del self.objects[:]
        self.nested = 0


class LayoutHints:
    """Per dirty layout: content ids to take out, and item ids to (re)place."""

    __slots__ = ("removed", "items")

    def __init__(self) -> None:
        self.removed: Set[NodeId] = set()
        self.items: Set[NodeId] = set()


def collect_layout_hints(
    changeset: ChangeSet,
    document: object,
    slot_of: Dict[NodeId, NodeId],
) -> Dict[NodeId, LayoutHints]:
    """O(changes). Removals are found through ``slot_of``, so a parent that left
    the document in the same ChangeSet still gets its hint."""
    hints: Dict[NodeId, LayoutHints] = {}

    def hint(layout_id: NodeId) -> LayoutHints:
        found = hints.get(layout_id)
        if found is None:
            found = hints[layout_id] = LayoutHints()
        return found

    def placed_into(parent_id: NodeId, node_id: NodeId) -> None:
        parent = document.get(parent_id)  # type: ignore[attr-defined]
        if isinstance(parent, LayoutNode):
            hint(parent.id).items.add(node_id)
        elif isinstance(parent, LayoutItemNode) and parent.parent_id is not None:
            hint(parent.parent_id).items.add(parent.id)

    def taken_from(node_id: NodeId) -> None:
        layout_id = slot_of.get(node_id)
        if layout_id is not None:
            hint(layout_id).removed.add(node_id)

    for change in changeset.changes:
        if isinstance(change, NodeInserted):
            placed_into(change.parent, change.node)
        elif isinstance(change, NodeRemoved):
            for node_id in change.subtree:
                taken_from(node_id)
            parent = document.get(change.parent)  # type: ignore[attr-defined]
            if isinstance(parent, LayoutNode):
                hint(parent.id)
            elif isinstance(parent, LayoutItemNode) and parent.parent_id is not None:
                hint(parent.parent_id)
        elif isinstance(change, NodeMoved):
            taken_from(change.node)
            moved = document.get(change.node)  # type: ignore[attr-defined]
            if isinstance(moved, LayoutItemNode) and moved.content is not None:
                taken_from(moved.content.id)
            old_parent = document.get(change.old_parent)  # type: ignore[attr-defined]
            if isinstance(old_parent, LayoutNode):
                hint(old_parent.id)
            elif isinstance(old_parent, LayoutItemNode) and old_parent.parent_id is not None:
                hint(old_parent.parent_id)
            placed_into(change.new_parent, change.node)
        elif isinstance(change, FieldChanged) and change.field in LAYOUT_ITEM_FIELDS:
            node = document.get(change.node)  # type: ignore[attr-defined]
            if isinstance(node, LayoutItemNode) and node.parent_id is not None:
                hint(node.parent_id).items.add(node.id)
    return hints


class _LayoutSlots:
    """Methods mixed into ``Realizer``. Attributes live on the realizer."""

    # -- mirror bookkeeping -------------------------------------------------

    def _mirror(self, layout_id: NodeId, qlayout: QLayout) -> Optional[_Mirror]:
        """The mirror of ``qlayout`` when it can be trusted, else None."""
        found = self._placed.get(layout_id)
        if found is None or found.layout is not qlayout:
            return None
        if not wrapper_is_valid(qlayout) or qlayout.count() != len(found):
            self._forget_slots(layout_id)
            return None
        return found

    def _take_from_slot(self, content_id: NodeId, obj: object) -> bool:
        """Take ``obj`` out of the layout the mirror says holds it."""
        layout_id = self._slot_of.pop(content_id, None)
        if layout_id is None:
            return False
        qlayout = self._layouts.get(layout_id)
        mirror = None if qlayout is None else self._mirror(layout_id, qlayout)
        if mirror is None:
            return False
        index = mirror.find(content_id)
        if index < 0 or mirror.objects[index] is not obj:
            return False
        self._take_entry(layout_id, mirror, index)
        return True

    def _take_entry(self, layout_id: NodeId, mirror: _Mirror, index: int) -> Tuple[NodeId, object]:
        qlayout = mirror.layout
        if isinstance(qlayout, QGridLayout) and _on_grid_edge(qlayout, mirror.fields[index]):
            self._grid_check.add(layout_id)
        qlayout.takeAt(index)
        content_id, obj = mirror.remove(index)
        if self._slot_of.get(content_id) == layout_id:
            del self._slot_of[content_id]
        return content_id, obj

    def _forget_slots(self, layout_id: NodeId) -> None:
        found = self._placed.pop(layout_id, None)
        if found is None:
            return
        for content_id in found.ids:
            if self._slot_of.get(content_id) == layout_id:
                del self._slot_of[content_id]

    # -- reconcile ------------------------------------------------------------

    def _fill_layout(self, node: LayoutNode, host: Optional[QWidget] = None) -> QLayout:
        install_host = None
        owner_id = node.owner_widget_id()
        if owner_id is not None:
            install_host = self._widgets.get(owner_id)
        if host is None:
            host = install_host
        taken: Taken = []
        hints = self._layout_hints.pop(node.id, None)
        if node.id in self._crowded:
            # A form with a shared cell: document order picks the item Qt keeps.
            hints = None
            self._filled.discard(node.id)
        if node.class_name == "QGridLayout" and node.id in self._grid_check:
            self._grid_check.discard(node.id)
            taken.extend(self._drop_oversized_grid(node))
        qlayout = self._ensure_layout(node, install_host)
        parent = host if host is not None else qlayout.parentWidget()
        kind = _kind_of(qlayout)
        mirror = self._mirror(node.id, qlayout)
        if mirror is not None and hints is None and node.id in self._filled:
            # Filled earlier in this patch and nothing changed since.
            self._release_taken(taken)
            return qlayout
        self._filled.add(node.id)
        done = False
        if mirror is not None and hints is not None:
            done = self._patch_layout(node, qlayout, kind, mirror, hints, parent, host, taken)
        if not done:
            self._diff_layout(node, qlayout, kind, parent, host, taken)
        self._release_taken(taken)
        if kind == _GRID and node.id in self._grid_check:
            self._grid_check.discard(node.id)
            if _grid_oversized(qlayout, node):
                self._grid_check.add(node.id)
                self._filled.discard(node.id)
                return self._fill_layout(node, host)
        self._apply_stretches(node, qlayout)
        if kind == _BOX:
            _reset_extra_stretch(node, qlayout)
        elif kind == _FORM:
            _trim_form_rows(qlayout, node)
        return qlayout

    def _patch_layout(
        self,
        node: LayoutNode,
        qlayout: QLayout,
        kind: str,
        mirror: _Mirror,
        hints: LayoutHints,
        parent: Optional[QWidget],
        host: Optional[QWidget],
        taken: Taken,
    ) -> bool:
        """O(changed): take out what the hints name, place the hinted items.

        Returns False when the hints do not settle the layout, and the caller
        diffs every item instead.
        """
        document = self._session.document
        doomed = set(hints.removed)
        items: List[LayoutItemNode] = []
        for item_id in hints.items:
            item = document.get(item_id)
            if not isinstance(item, LayoutItemNode) or item.parent_id != node.id:
                continue
            items.append(item)
            content = item.content
            if content is not None:
                doomed.add(content.id)
        for content_id in doomed:
            index = mirror.find(content_id)
            if index >= 0:
                taken.append(self._take_entry(node.id, mirror, index))
        items.sort(key=lambda each: each.slot_index)
        for item in items:
            content = item.content
            if content is None:
                continue
            if kind == _BOX:
                index = _box_index(node, item, mirror)
                if index < 0:
                    return False
            else:
                index = len(mirror)
            if kind == _FORM and _form_cell_taken(qlayout, item.row or 0, _form_column(item)):
                # Which item keeps a shared cell depends on document order.
                return False
            self._place(node, qlayout, kind, item, index, parent, host)
        return True

    def _diff_layout(
        self,
        node: LayoutNode,
        qlayout: QLayout,
        kind: str,
        parent: Optional[QWidget],
        host: Optional[QWidget],
        taken: Taken,
    ) -> None:
        """Compare every document item with the mirror. O(items)."""
        self._crowded.discard(node.id)
        want = [item for item in (_form_order(node) if kind == _FORM else node.items) if item.content is not None]
        mirror = self._mirror(node.id, qlayout)
        if mirror is None or (kind == _FORM and _shares_a_cell(want)):
            taken.extend(self._take_all(node.id, qlayout))
            mirror = _Mirror(qlayout)
            self._placed[node.id] = mirror
            if kind == _GRID:
                self._grid_check.add(node.id)
        wanted: Dict[NodeId, Tuple[object, object]] = {}
        for item in want:
            content = item.content
            wanted[content.id] = (item.fields, self._live_object(content))  # type: ignore[union-attr]
        for index in range(len(mirror) - 1, -1, -1):
            match = wanted.get(mirror.ids[index])
            if match is not None and match[1] is mirror.objects[index] and match[0] == mirror.fields[index]:
                continue
            taken.append(self._take_entry(node.id, mirror, index))
        missing: List[int] = []
        if kind != _BOX:
            # Grid and form items carry their own cell, so order does not matter.
            kept = set(mirror.ids)
            missing = [index for index, item in enumerate(want) if item.content.id not in kept]  # type: ignore[union-attr]
            for index in missing:
                self._place(node, qlayout, kind, want[index], len(mirror), parent, host)
            return
        cursor = 0
        for index, item in enumerate(want):
            if cursor < len(mirror) and mirror.ids[cursor] == item.content.id:  # type: ignore[union-attr]
                cursor += 1
                continue
            missing.append(index)
        if cursor != len(mirror):
            # Kept items are out of document order. Start this layout over.
            taken.extend(self._take_all(node.id, qlayout))
            mirror = _Mirror(qlayout)
            self._placed[node.id] = mirror
            missing = list(range(len(want)))
        for index in missing:
            self._place(node, qlayout, kind, want[index], index, parent, host)

    def _live_object(self, content: object) -> Optional[object]:
        node_id = content.node_id  # type: ignore[attr-defined]
        if isinstance(content, WidgetNode):
            return self._widgets.get(node_id)
        if isinstance(content, LayoutNode):
            return self._layouts.get(node_id)
        if isinstance(content, SpacerNode):
            return self._spacers.get(node_id)
        return None

    def _place(
        self,
        node: LayoutNode,
        qlayout: QLayout,
        kind: str,
        item: LayoutItemNode,
        index: int,
        parent: Optional[QWidget],
        host: Optional[QWidget],
    ) -> None:
        content = item.content
        if isinstance(content, WidgetNode):
            obj: object = self._obtain_widget(content, parent)
        elif isinstance(content, LayoutNode):
            obj = self._nested_layout(content, host)
        elif isinstance(content, SpacerNode):
            obj = self._spacer(content)
        else:
            return
        if kind == _FORM:
            if not self._place_form(node, qlayout, item, obj):  # type: ignore[arg-type]
                return
        elif kind == _GRID:
            _place_grid(qlayout, item, obj)  # type: ignore[arg-type]
        else:
            _place_box(qlayout, item, obj, index)
        mirror = self._placed.get(node.id)
        if mirror is None or mirror.layout is not qlayout:
            mirror = _Mirror(qlayout)
            self._placed[node.id] = mirror
        mirror.insert(index, item.fields, content.id, obj)
        self._slot_of[content.id] = node.id

    def _nested_layout(self, content: LayoutNode, host: Optional[QWidget]) -> QLayout:
        nested = self._fill_layout(content, host)
        parent = nested.parent()
        if isinstance(parent, QWidget) and parent.layout() is nested:
            # This object is still some widget's own layout. It cannot also be
            # an item, so drop it and build the nested one fresh.
            self._delete_layout_object(nested)
            nested = self._fill_layout(content, host)
            parent = nested.parent()
        if parent is not None:
            if not self._take_from_slot(content.id, nested) and isinstance(parent, QLayout):
                parent.removeItem(nested)
            if nested.parent() is not None:
                nested.setParent(None)
        return nested

    def _place_form(self, node: LayoutNode, qlayout: QFormLayout, item: LayoutItemNode, obj: object) -> bool:
        row = item.row or 0
        role = _form_role(item)
        if _form_cell_taken(qlayout, row, _form_column(item)):
            self._report_taken_cell(node, item)
            self._unplaced.add(item.content.id)  # type: ignore[union-attr]
            self._crowded.add(node.id)
            if isinstance(obj, QLayout):
                # Nothing installs it, so it must not keep items either.
                self._detach_layout(obj)
            return False
        if isinstance(obj, QWidget):
            qlayout.setWidget(row, role, obj)
        elif isinstance(obj, QLayout):
            qlayout.setLayout(row, role, obj)
        else:
            qlayout.setItem(row, role, obj)  # type: ignore[arg-type]
        return True

    def _report_taken_cell(self, node: LayoutNode, item: LayoutItemNode) -> None:
        content = item.content
        name = getattr(content, "object_name", "") or getattr(content, "name", "") or str(int(content.id))  # type: ignore[union-attr]
        problem = "form layout %s: row %d %s cell is taken; %s is not placed" % (
            node.object_name,
            item.row or 0,
            "label" if _form_column(item) == 0 else "field",
            name,
        )
        if problem not in self._problems:
            self._problems.append(problem)
            logger.warning("FB902 %s", problem)

    def _take_all(self, layout_id: NodeId, qlayout: QLayout) -> Taken:
        """Take every item out. Widgets stay parented until the caller decides."""
        self._forget_slots(layout_id)
        taken: Taken = []
        while qlayout.count():
            item = qlayout.takeAt(qlayout.count() - 1)
            if item is None:
                break
            child = item.widget()
            if child is not None:
                taken.append((_node_id(child), child))
                continue
            nested = item.layout()
            if nested is not None:
                taken.append((_node_id(nested), nested))
                continue
            spacer_id = self._spacer_of(item)
            if spacer_id is not None:
                self._pool[spacer_id] = item
                taken.append((spacer_id, item))
        if isinstance(qlayout, QFormLayout):
            _clear_form_rows(qlayout)
        taken.reverse()
        return taken

    def _release_taken(self, taken: Taken) -> None:
        """Pool what a reconcile took out and did not put back anywhere."""
        for content_id, obj in taken:
            if content_id is not None and content_id in self._slot_of:
                continue
            if isinstance(obj, QWidget):
                if not wrapper_is_valid(obj):
                    continue
                if content_id is not None and content_id in self._unplaced:
                    continue
                # Parked in place. A container takes it back within the window,
                # or destroy and the sweep delete it where it is.
                if content_id is not None:
                    self._hold_widget(content_id, obj)
                else:
                    obj.setParent(None)
            elif isinstance(obj, QLayout):
                if not wrapper_is_valid(obj) or isinstance(obj.parent(), QWidget):
                    # Gone, or installed as some widget's own layout.
                    continue
                self._detach_layout(obj)
                if obj.parent() is not None:
                    obj.setParent(None)
            elif content_id is not None:
                self._pool[content_id] = obj
        del taken[:]

    def _detach_layout(self, qlayout: QLayout) -> None:
        """Empty ``qlayout`` into the pool, nested layouts included."""
        layout_id = _node_id(qlayout)
        if layout_id is not None:
            self._forget_slots(layout_id)
        while qlayout.count():
            item = qlayout.takeAt(qlayout.count() - 1)
            if item is None:
                break
            self._pool_taken_item(item)
        if isinstance(qlayout, QFormLayout):
            _clear_form_rows(qlayout)

    def _pool_taken_item(self, item: object) -> None:
        child = item.widget() if hasattr(item, "widget") else None  # type: ignore[attr-defined]
        if child is not None:
            node_id = _node_id(child)
            if node_id is not None:
                self._hold_widget(node_id, child)
            child.setParent(None)
            return
        nested = item.layout() if hasattr(item, "layout") else None  # type: ignore[attr-defined]
        if nested is not None:
            # Out of the tree means empty: its items would outlive their widgets.
            self._detach_layout(nested)
            if nested.parent() is not None and not isinstance(nested.parent(), QWidget):
                nested.setParent(None)
            return
        spacer_id = self._spacer_of(item)
        if spacer_id is not None:
            self._pool[spacer_id] = item

    def _spacer_of(self, item: object) -> Optional[NodeId]:
        return self._spacer_ids.get(id(item))


def _node_id(obj: object) -> Optional[NodeId]:
    if obj is None or not hasattr(obj, "property"):
        return None
    raw = obj.property(NODE_ID_PROPERTY)  # type: ignore[attr-defined]
    if raw is None or raw == "":
        return None
    try:
        return NodeId(int(raw))
    except (TypeError, ValueError):
        return None


def _kind_of(qlayout: QLayout) -> str:
    if isinstance(qlayout, QFormLayout):
        return _FORM
    if isinstance(qlayout, QGridLayout):
        return _GRID
    return _BOX


def _box_index(node: LayoutNode, item: LayoutItemNode, mirror: _Mirror) -> int:
    """Qt index for ``item``: one past the nearest earlier sibling already placed."""
    siblings = node.children("layout_items")
    position = item.slot_index
    if position >= len(siblings) or siblings[position] is not item:
        return -1
    for back in range(position - 1, -1, -1):
        sibling = siblings[back]
        content = sibling.content if isinstance(sibling, LayoutItemNode) else None
        if content is None:
            continue
        found = mirror.find(content.id)
        if found >= 0:
            return found + 1
    return 0


def _place_box(qlayout: QLayout, item: LayoutItemNode, obj: object, index: int) -> None:
    box = isinstance(qlayout, QBoxLayout)
    if isinstance(obj, QWidget):
        if box:
            qlayout.insertWidget(index, obj)  # type: ignore[attr-defined]
        else:
            qlayout.addWidget(obj)
        _align(qlayout, obj, item)
    elif isinstance(obj, QLayout):
        if box:
            qlayout.insertLayout(index, obj)  # type: ignore[attr-defined]
        else:
            qlayout.addLayout(obj)  # type: ignore[attr-defined]
    elif box:
        qlayout.insertItem(index, obj)  # type: ignore[attr-defined]
    else:
        qlayout.addItem(obj)  # type: ignore[arg-type]


def _place_grid(qlayout: QGridLayout, item: LayoutItemNode, obj: object) -> None:
    row = item.row or 0
    column = item.column or 0
    rowspan = item.rowspan or 1
    colspan = item.colspan or 1
    if isinstance(obj, QWidget):
        qlayout.addWidget(obj, row, column, rowspan, colspan)
        _align(qlayout, obj, item)
    elif isinstance(obj, QLayout):
        qlayout.addLayout(obj, row, column, rowspan, colspan)
    else:
        qlayout.addItem(obj, row, column, rowspan, colspan)  # type: ignore[arg-type]


def _align(qlayout: QLayout, widget: QWidget, item: LayoutItemNode) -> None:
    if not item.alignment:
        return
    flag = resolve_enum(item.alignment)
    if flag is None:
        return
    try:
        qlayout.setAlignment(widget, flag)
    except (TypeError, AttributeError):
        return


def _on_grid_edge(qlayout: QGridLayout, fields: object) -> bool:
    """Whether an item with these fields reaches the grid's last row or column."""
    values = dict(fields)  # type: ignore[call-overload]
    row = _int_or(values.get("row"), 0)
    column = _int_or(values.get("column"), 0)
    rowspan = _int_or(values.get("rowspan"), 1)
    colspan = _int_or(values.get("colspan"), 1)
    return row + rowspan >= qlayout.rowCount() or column + colspan >= qlayout.columnCount()


def _grid_oversized(qlayout: QGridLayout, node: LayoutNode) -> bool:
    rows, columns = grid_extent(node)
    return qlayout.rowCount() > rows or qlayout.columnCount() > columns


def grid_extent(node: LayoutNode) -> Tuple[int, int]:
    """Rows and columns a fresh grid reports, which is at least 1."""
    rows = 1
    columns = 1
    for item in node.items:
        if item.content is None:
            continue
        rows = max(rows, (item.row or 0) + (item.rowspan or 1))
        columns = max(columns, (item.column or 0) + (item.colspan or 1))
    for field_name, axis in (
        ("rowstretch", "rows"),
        ("rowminimumheight", "rows"),
        ("columnstretch", "columns"),
        ("columnminimumwidth", "columns"),
    ):
        raw = node.field(field_name)
        if not isinstance(raw, str) or not raw.strip():
            continue
        length = 0
        for index, piece in enumerate(part.strip() for part in raw.split(",")):
            if piece:
                length = index + 1
        if axis == "rows":
            rows = max(rows, length)
        else:
            columns = max(columns, length)
    return rows, columns


def _int_or(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _form_order(node: LayoutNode) -> Tuple[LayoutItemNode, ...]:
    return tuple(sorted(node.items, key=lambda item: (item.row or 0, item.column or 0)))


def _form_role(item: LayoutItemNode) -> object:
    role_type = getattr(QFormLayout, "ItemRole", QFormLayout)
    colspan = item.colspan or 1
    column = item.column or 0
    if colspan > 1 or column >= 2:
        return getattr(role_type, "SpanningRole")
    if column == 1:
        return getattr(role_type, "FieldRole")
    return getattr(role_type, "LabelRole")


def _form_column(item: LayoutItemNode) -> int:
    """Qt's storage column: 0 for a label, 1 for a field or a spanning row."""
    colspan = item.colspan or 1
    column = item.column or 0
    return 1 if colspan > 1 or column >= 1 else 0


def _form_cell_taken(qlayout: QFormLayout, row: int, column: int) -> bool:
    if row >= qlayout.rowCount():
        return False
    role_type = getattr(QFormLayout, "ItemRole", QFormLayout)
    role = getattr(role_type, "FieldRole" if column == 1 else "LabelRole")
    return qlayout.itemAt(row, role) is not None


def _shares_a_cell(want: List[LayoutItemNode]) -> bool:
    """Qt keeps the first item in a cell. Document order decides which is first."""
    seen: Set[Tuple[int, int]] = set()
    for item in want:
        cell = (item.row or 0, _form_column(item))
        if cell in seen:
            return True
        seen.add(cell)
    return False


def _clear_form_rows(qlayout: QFormLayout) -> None:
    while qlayout.rowCount():
        qlayout.removeRow(qlayout.rowCount() - 1)


def _trim_form_rows(qlayout: QFormLayout, node: LayoutNode) -> None:
    """A fresh form has max(row) + 1 rows. Drop trailing rows a removal emptied."""
    role_type = getattr(QFormLayout, "ItemRole", QFormLayout)
    label = getattr(role_type, "LabelRole")
    field = getattr(role_type, "FieldRole")
    last = qlayout.rowCount() - 1
    if last < 0 or qlayout.itemAt(last, label) is not None or qlayout.itemAt(last, field) is not None:
        return
    needed = 0
    for item in node.items:
        if item.content is not None:
            needed = max(needed, (item.row or 0) + 1)
    while qlayout.rowCount() > needed:
        last = qlayout.rowCount() - 1
        if qlayout.itemAt(last, label) is not None or qlayout.itemAt(last, field) is not None:
            return
        qlayout.removeRow(last)


def _reset_extra_stretch(node: LayoutNode, qlayout: QLayout) -> None:
    """Kept items keep their stretch. Indexes past the document's list go back to 0."""
    if not isinstance(qlayout, QBoxLayout):
        return
    raw = node.field("stretch")
    given = len(raw.split(",")) if isinstance(raw, str) else 0
    for index in range(given, qlayout.count()):
        if qlayout.stretch(index):
            qlayout.setStretch(index, 0)
