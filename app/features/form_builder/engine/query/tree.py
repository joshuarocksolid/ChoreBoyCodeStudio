"""Read-only query helpers and layout math (CONTRACTS.md section 2.8).

Pure functions of a document. None of them mutates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

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
    }
)

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


def grid_shape(doc: UiDocument, layout_id: NodeId) -> GridShape:
    """O(items)."""
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
    return GridShape(rows, columns, tuple(cells), tuple(empty), tuple(overlaps))


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
            column = item.column if item.column is not None else 0
            colspan = item.colspan if item.colspan is not None else 1
            if colspan >= 2 or (column == 0 and colspan == 2):
                spanning = item.id
            elif column <= 0:
                label = item.id
            else:
                field = item.id
        found.append((label, field, spanning))
    return tuple(found)


def visual_children(doc: UiDocument, widget_id: NodeId) -> Tuple[NodeId, ...]:
    """Layout contents, or the direct child widgets when there is no layout. O(children)."""
    widget = doc.node(widget_id)
    if not isinstance(widget, WidgetNode):
        return ()
    if widget.layout is None:
        return tuple(child.id for child in widget.child_widgets)
    return _layout_content_ids(widget.layout)


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
    """Insert new inputs where they sit in reading order. O(n)."""
    result = list(order)
    reading_at = {name: index for index, name in enumerate(reading)}
    for name in new_names:
        if name in result:
            continue
        spot = reading_at.get(name)
        if spot is None:
            result.append(name)
            continue
        insert_at = len(result)
        for index, existing in enumerate(result):
            existing_at = reading_at.get(existing)
            if existing_at is not None and existing_at > spot:
                insert_at = index
                break
        result.insert(insert_at, name)
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
    if widget.class_name in _FOCUSABLE and widget.object_name:
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
