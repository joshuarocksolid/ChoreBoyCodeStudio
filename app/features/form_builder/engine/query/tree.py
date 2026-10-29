"""Read-only query helpers and layout math (CONTRACTS.md section 2.8).

Pure functions of a document. None of them mutates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Literal, Optional, Tuple
from weakref import WeakKeyDictionary

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import CStringValue, EnumValue, StringValue

# Used when the class table has not been generated yet. A known class trusts
# its flags and ignores this set.
PAGE_CONTAINERS = frozenset(
    {
        "QTabWidget",
        "QStackedWidget",
        "QToolBox",
        "QSplitter",
        "QWizard",
        "QMdiArea",
    }
)

_FALLBACK_CONTAINERS = PAGE_CONTAINERS | frozenset(
    {
        "QWidget",
        "QFrame",
        "QGroupBox",
        "QScrollArea",
        "QMainWindow",
        "QDialog",
        "QDockWidget",
        "QWizardPage",
        "QMenu",
        "QToolBar",
        "QMenuBar",
        "QStatusBar",
    }
)

_FOCUSABLE = frozenset(
    {
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QComboBox",
        "QFontComboBox",
        "QSpinBox",
        "QDoubleSpinBox",
        "QCheckBox",
        "QRadioButton",
        "QPushButton",
        "QToolButton",
        "QCommandLinkButton",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QDial",
        "QSlider",
        "QListWidget",
        "QTableWidget",
        "QTreeWidget",
        "QKeySequenceEdit",
        "QListView",
        "QTreeView",
        "QTableView",
        "QTextBrowser",
        # Containers whose default policy has the Tab bit (Qt 6.8 and 5.15 agree).
        "QScrollArea",
        "QAbstractScrollArea",
        "QTabWidget",
        "QGraphicsView",
        "QCalendarWidget",
        "QColumnView",
        "QUndoView",
        "QAbstractSpinBox",
        "QMdiSubWindow",
        # QDialogButtonBox is NoFocus: Tab lands on its buttons, which Designer does
        # not number, and QWidget::setTabOrder ignores a NoFocus widget, so a
        # buttonBox <tabstop> would break the chain at runtime.
    }
)

#: ``focusPolicy`` enumerators that include the Tab bit (UX-MODE-003).
_TAB_POLICIES = frozenset({"TabFocus", "StrongFocus"})

_FORM_KIND = {
    "QMainWindow": "main_window",
    "QDialog": "dialog",
    "QWizard": "wizard",
    "QWidget": "widget",
}


@dataclass(frozen=True)
class GridCell:
    item: NodeId
    row: int
    column: int
    rowspan: int
    colspan: int


@dataclass(frozen=True)
class GridShape:
    """Occupancy of a QGridLayout or QFormLayout."""

    rows: int
    columns: int
    cells: Tuple[GridCell, ...]
    empty: Tuple[Tuple[int, int], ...]
    overlaps: Tuple[Tuple[NodeId, NodeId], ...]


_SHAPES: WeakKeyDictionary = WeakKeyDictionary()


def grid_shape(doc: UiDocument, layout_id: NodeId) -> GridShape:
    """O(items) the first time this revision reads ``layout_id``. Later reads reuse that shape.

    A selection pass asks for the same grid once for the survey and again for every handle.
    """
    generation = _SHAPES.get(doc)
    shapes: Dict[NodeId, GridShape]
    if generation is not None and generation[0] == doc.revision:
        shapes = generation[1]
    else:
        shapes = {}
        _SHAPES[doc] = (doc.revision, shapes)
    found = shapes.get(layout_id)
    if found is not None:
        return found
    cells = _cells(doc, layout_id)
    rows = 0
    columns = 0
    covered: Dict[Tuple[int, int], List[NodeId]] = {}
    for cell in cells:
        rows = max(rows, cell.row + cell.rowspan)
        columns = max(columns, cell.column + cell.colspan)
        for row in range(cell.row, cell.row + cell.rowspan):
            for column in range(cell.column, cell.column + cell.colspan):
                covered.setdefault((row, column), []).append(cell.item)
    empty: List[Tuple[int, int]] = []
    overlaps: List[Tuple[NodeId, NodeId]] = []
    seen = set()
    for row in range(rows):
        for column in range(columns):
            owners = covered.get((row, column), [])
            if not owners:
                empty.append((row, column))
            elif len(owners) > 1:
                pair = (owners[0], owners[1])
                if pair not in seen:
                    seen.add(pair)
                    overlaps.append(pair)
    shape = GridShape(rows, columns, tuple(cells), tuple(empty), tuple(overlaps))
    shapes[layout_id] = shape
    return shape


def blocked(shape: GridShape, cell: GridCell) -> bool:
    """True when ``cell`` covers a cell another item holds."""
    for other in shape.cells:
        if other.item == cell.item:
            continue
        if (
            cell.row < other.row + other.rowspan
            and other.row < cell.row + cell.rowspan
            and cell.column < other.column + other.colspan
            and other.column < cell.column + cell.colspan
        ):
            return True
    return False


def effective_class(doc: UiDocument, node: WidgetNode) -> str:
    """The Qt class a promoted widget extends, else its own class."""
    custom = doc.custom_widget(node.class_name)
    if isinstance(custom, CustomWidgetNode) and custom.extends:
        return custom.extends.split("::")[-1]
    return node.class_name


def next_free_cell(
    doc: UiDocument,
    layout_id: NodeId,
    *,
    columns_hint: int = 2,
) -> Tuple[int, int, str]:
    """The next cell a drop fills. O(items)."""
    layout = doc.node(layout_id)
    if isinstance(layout, LayoutNode) and layout.class_name == "QFormLayout":
        rows = form_rows(doc, layout_id)
        for index, (label, field, spanning) in enumerate(rows):
            if spanning is None and label is None:
                return (index, 0, "label")
            if spanning is None and field is None:
                return (index, 1, "field")
        return (len(rows), 0, "label")
    shape = grid_shape(doc, layout_id)
    if shape.empty:
        row, column = shape.empty[0]
        return (row, column, "cell")
    if shape.rows == 0:
        return (0, 0, "cell")
    if shape.columns < columns_hint:
        return (shape.rows - 1, shape.columns, "cell")
    return (shape.rows, 0, "cell")


def form_rows(
    doc: UiDocument,
    layout_id: NodeId,
) -> Tuple[Tuple[Optional[NodeId], Optional[NodeId], Optional[NodeId]], ...]:
    """QFormLayout rows as (label item, field item, spanning item). O(items)."""
    by_row: Dict[int, List[LayoutItemNode]] = {}
    for item in _items(doc, layout_id):
        row = item.row if item.row is not None else 0
        by_row.setdefault(row, []).append(item)
    if not by_row:
        return ()
    found = []
    for row in range(max(by_row) + 1):
        label = None
        field = None
        spanning = None
        for item in by_row.get(row, ()):
            role = form_item_role(item.column, item.colspan)
            if role == "spanning":
                spanning = item.id
            elif role == "label":
                label = item.id
            else:
                field = item.id
        found.append((label, field, spanning))
    return tuple(found)


def form_item_role(
    column: Optional[int], colspan: Optional[int]
) -> Literal["label", "field", "spanning"]:
    """Role of one QFormLayout item. O(1)."""
    span = 1 if colspan is None or colspan == 0 else colspan
    col = 0 if column is None else column
    if span > 1:
        return "spanning"
    if col == 0:
        return "label"
    return "field"


def form_occupied_cells(
    row: Optional[int],
    column: Optional[int],
    colspan: Optional[int],
) -> FrozenSet[Tuple[int, str]]:
    """The (row, role) cells a QFormLayout item takes. Spanning takes both. O(1)."""
    r = 0 if row is None else row
    role = form_item_role(column, colspan)
    if role == "spanning":
        return frozenset(((r, "label"), (r, "field")))
    return frozenset(((r, role),))


def form_collision_groups(doc: UiDocument) -> FrozenSet[FrozenSet[NodeId]]:
    """Ids of items that share a QFormLayout cell. O(form)."""
    groups = set()
    for node in doc.iter_preorder():
        if not isinstance(node, LayoutNode) or node.class_name != "QFormLayout":
            continue
        buckets: Dict[Tuple[int, str], List[NodeId]] = {}
        for item in node.items:
            for cell in form_occupied_cells(item.row, item.column, item.colspan):
                buckets.setdefault(cell, []).append(item.id)
        for ids in buckets.values():
            if len(ids) > 1:
                groups.add(frozenset(ids))
    return frozenset(groups)


def visual_children(doc: UiDocument, widget_id: NodeId) -> Tuple[NodeId, ...]:
    """Layout contents, or the direct child widgets when there is no layout. O(children)."""
    widget = doc.node(widget_id)
    if not isinstance(widget, WidgetNode):
        return ()
    if widget.layout is None:
        return tuple(child.id for child in widget.child_widgets)
    return _layout_content_ids(widget.layout)


def takes_tab_focus(widget: WidgetNode) -> bool:
    """True when Tab can land on the widget: its ``focusPolicy`` has the Tab bit, or the class does by default. O(1)."""
    policy = widget.prop("focusPolicy")
    if policy is not None and isinstance(policy.value, EnumValue):
        return policy.value.text.rsplit("::", 1)[-1] in _TAB_POLICIES
    return widget.class_name in _FOCUSABLE


def reading_order(doc: UiDocument) -> Tuple[str, ...]:
    """Focusable widget names in visual reading order. O(form)."""
    names: List[str] = []
    _walk_reading(doc, doc.root, names)
    return tuple(names)


def effective_tab_order(doc: UiDocument) -> Tuple[str, ...]:
    """Saved tab stops that still exist, otherwise the reading order. O(form)."""
    saved = doc.tabstops()
    if saved is None:
        return reading_order(doc)
    alive = doc.names()
    return tuple(name for name in saved if name in alive)


def splice_tab_order(
    order: Tuple[str, ...],
    reading: Tuple[str, ...],
    new_names: Tuple[str, ...],
) -> Tuple[str, ...]:
    """Put each new input right after the stop that precedes it on the form (UX-OVL-006, pain 20).

    A new input with nothing before it goes in front of the stop that follows it;
    one the form does not place goes last. New inputs are joined in reading order.
    O(n * m).
    """
    result = list(order)
    reading_at = {name: index for index, name in enumerate(reading)}
    placed = sorted((name for name in new_names if name not in result), key=lambda name: reading_at.get(name, len(reading)))
    for name in placed:
        spot = reading_at.get(name)
        if spot is None:
            result.append(name)
            continue
        before = -1
        before_at = -1
        after = -1
        after_at = len(reading) + 1
        for index, existing in enumerate(result):
            existing_at = reading_at.get(existing)
            if existing_at is None:
                continue
            if existing_at < spot and existing_at > before_at:
                before, before_at = index, existing_at
            elif existing_at > spot and existing_at < after_at:
                after, after_at = index, existing_at
        if before >= 0:
            result.insert(before + 1, name)
        elif after >= 0:
            result.insert(after, name)
        else:
            result.append(name)
    return tuple(result)


def child_stack_order(doc: UiDocument, parent_id: NodeId) -> Tuple[str, ...]:
    """Bottom-to-top child widget names, from the real child list. O(children)."""
    widget = doc.node(parent_id)
    if not isinstance(widget, WidgetNode):
        return ()
    names = [child.object_name for child in widget.child_widgets if child.object_name]
    present = set(names)
    listed = [name for name in widget.zorder if name in present]
    listed_set = set(listed)
    return tuple(listed + [name for name in names if name not in listed_set])


def references_to(doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
    """Native references to ``name``. Logic references come from participants. O(form)."""
    found: List[Tuple[NodeId, str]] = []
    for node in doc.iter_preorder():
        if node.kind == "connection":
            if node.field("sender") == name:
                found.append((node.id, "connection.sender"))
            if node.field("receiver") == name:
                found.append((node.id, "connection.receiver"))
        elif node.kind == "action" and node.field("menu") == name:
            found.append((node.id, "action.menu"))
        elif node.kind == "actionref" and node.field("name") == name:
            found.append((node.id, "addaction"))
        elif node.kind == "widget":
            zorder = node.field("zorder")
            if isinstance(zorder, tuple) and name in zorder:
                found.append((node.id, "zorder"))
            buddy = node.prop("buddy")
            if buddy is not None and _entry_text(buddy.value) == name:
                found.append((node.id, "buddy"))
            group = node.attr("buttonGroup")
            if group is not None and _entry_text(group.value) == name:
                found.append((node.id, "buttonGroup"))
        elif node.kind == "ui":
            stops = node.field("tabstops")
            if isinstance(stops, tuple) and name in stops:
                found.append((node.id, "tabstop"))
    return tuple(found)


def page_children(doc: UiDocument, widget_id: NodeId) -> Tuple[NodeId, ...]:
    """Pages of a page container, in page order. O(children)."""
    if not is_page_container(doc, widget_id):
        return ()
    widget = doc.node(widget_id)
    if not isinstance(widget, WidgetNode):
        return ()
    return tuple(child.id for child in widget.child_widgets)


def is_page_container(doc: UiDocument, widget_id: NodeId) -> bool:
    """QTabWidget, QStackedWidget, QToolBox, QSplitter, QWizard, QMdiArea. O(1)."""
    node = doc.get(widget_id)
    if not isinstance(node, WidgetNode):
        return False
    flags = _flags(node.class_name)
    if flags is not None:
        return "page_container" in flags
    return node.class_name in PAGE_CONTAINERS


def is_container(doc: UiDocument, widget_id: NodeId) -> bool:
    """A widget that can hold dropped widgets. O(1)."""
    node = doc.get(widget_id)
    if not isinstance(node, WidgetNode):
        return False
    if node.layout is not None:
        return True
    known = _known_container(doc, node.class_name)
    if known is not None:
        return known
    return node.class_name in _FALLBACK_CONTAINERS


def form_kind(doc: UiDocument) -> str:
    """``main_window``, ``dialog``, ``wizard``, ``widget`` or ``other``. O(1)."""
    return _FORM_KIND.get(doc.root.class_name, "other")


def _cells(doc: UiDocument, layout_id: NodeId) -> Tuple[GridCell, ...]:
    found = []
    for item in _items(doc, layout_id):
        found.append(
            GridCell(
                item=item.id,
                row=item.row if item.row is not None else 0,
                column=item.column if item.column is not None else 0,
                rowspan=item.rowspan if item.rowspan is not None else 1,
                colspan=item.colspan if item.colspan is not None else 1,
            )
        )
    return tuple(found)


def _items(doc: UiDocument, layout_id: NodeId) -> Tuple[LayoutItemNode, ...]:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return ()
    return layout.items


def _layout_content_ids(layout: LayoutNode) -> Tuple[NodeId, ...]:
    found = []
    for item in layout.items:
        content = item.content
        if content is not None:
            found.append(content.id)
    return tuple(found)


def _walk_reading(doc: UiDocument, widget: WidgetNode, names: List[str]) -> None:
    if takes_tab_focus(widget) and widget.object_name:
        names.append(widget.object_name)
    layout = widget.layout
    if layout is not None:
        _walk_layout(doc, layout, names)
        return
    for child in widget.child_widgets:
        _walk_reading(doc, child, names)


def _walk_layout(doc: UiDocument, layout: LayoutNode, names: List[str]) -> None:
    ordered = list(layout.items)
    if layout.class_name in ("QGridLayout", "QFormLayout"):
        ordered.sort(key=lambda item: (item.row or 0, item.column or 0, item.slot_index))
    for item in ordered:
        content = item.content
        if isinstance(content, WidgetNode):
            _walk_reading(doc, content, names)
        elif isinstance(content, LayoutNode):
            _walk_layout(doc, content, names)


def _flags(class_name: str) -> Optional[Tuple[str, ...]]:
    info = QtClassTable.shared().class_info(class_name)
    if info is None:
        return None
    return info.flags


def _known_container(doc: UiDocument, class_name: str) -> Optional[bool]:
    flags = _flags(class_name)
    if flags is not None:
        return "container" in flags or "page_container" in flags
    custom = doc.custom_widget(class_name)
    if custom is None:
        return None
    extends = custom.field("extends")
    if isinstance(extends, str):
        extended = _flags(extends)
        if extended is not None:
            return "container" in extended or "page_container" in extended
    value = custom.field("container")
    if value in (1, "1", True):
        return True
    return None


def _entry_text(value: object) -> Optional[str]:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None
