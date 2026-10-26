"""``GeometrySource`` over live widgets, and the ChangeSet invalidator (CONTRACTS.md section 5.5)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QRect, Qt
from app.qt.QtWidgets import QAbstractButton, QApplication, QGridLayout, QSplitter, QTabWidget, QToolBox, QWidget
from app.qt.qt_compat import enum_value
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.direct import (
    LayoutFacts,
    PrimaryFacts,
    SplitterFacts,
    Survey,
    SurveyScope,
    Track,
)
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.tree import GridShape, grid_shape
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, Node, SpacerNode, WidgetNode
from app.features.form_builder.qtside.canvas.core.structure import Free, free_origin, positioning_of
from app.features.form_builder.qtside.realize import NODE_ID_PROPERTY, Realizer
from app.features.form_builder.qtside.sizing_live import class_default_policies

# Layouts and spacers sit under any widget that shares their container.
_LAYOUT_Z = -1


class LiveGeometrySource:
    """One pre-order walk of the Qt widget tree under the root, adding up
    ``pos()`` offsets. Untagged intermediate widgets (a tab widget's stack, a
    scroll area's viewport) add their offset and emit nothing. A tagged
    widget's ``container`` is the layout that holds it, else its nearest
    tagged ancestor. ``z`` is the index among the Qt parent's children, which
    is Qt's paint order. The walk does not enter leaf widgets or hidden ones.
    """

    def __init__(self, realizer: Realizer) -> None:
        self._realizer = realizer

    def settle(self) -> None:
        root = self._realizer.root_widget
        if root is None:
            return
        # A nested widget's invalidated layout reports an empty geometry until
        # its own posted LayoutRequest runs. Root activation does not reach it.
        QApplication.sendPostedEvents(None, enum_value(QEvent.Type.LayoutRequest))
        layout = root.layout()
        if layout is not None:
            layout.activate()

    def entries(self) -> Sequence[GeoEntry]:
        root = self._realizer.root_widget
        document = self._realizer.document
        root_node = document.root
        if root is None or not isinstance(root_node, WidgetNode):
            return ()
        out: List[GeoEntry] = [GeoEntry(root_node.id, "widget", Rect(0, 0, root.width(), root.height()), None, True, 0)]
        self._titles(root, document, 0, 0, root_node.id, out)
        holder: Dict[NodeId, NodeId] = {}
        if root_node.layout is not None:
            self._layout_tree(root_node.layout, root_node.id, 0, 0, holder, out)
        stack: List[Tuple[QWidget, int, int, NodeId]] = [(root, 0, 0, root_node.id)]
        while stack:
            parent, px, py, owner = stack.pop()
            found: List[Tuple[QWidget, int, int, NodeId]] = []
            for z, child in enumerate(parent.children()):
                if not isinstance(child, QWidget) or child.isWindow():
                    continue
                x = px + child.x()
                y = py + child.y()
                # The walk never enters a hidden widget, so the child's own
                # flag is the same answer as isVisibleTo(root) and cheaper.
                visible = child.isVisible()
                node = _tagged_widget(child, document)
                if node is None:
                    if visible:
                        found.append((child, x, y, owner))
                    continue
                rect = Rect(x, y, child.width(), child.height())
                out.append(GeoEntry(node.id, "widget", rect, holder.get(node.id, owner), visible, z))
                if visible:
                    self._titles(child, document, x, y, node.id, out)
                if not visible:
                    continue
                if node.layout is not None:
                    self._layout_tree(node.layout, node.id, x, y, holder, out)
                if node.layout is not None or node.child_widgets:
                    found.append((child, x, y, node.id))
            stack.extend(reversed(found))
        return out

    def _layout_tree(
        self,
        top: LayoutNode,
        owner: NodeId,
        x: int,
        y: int,
        holder: Dict[NodeId, NodeId],
        out: List[GeoEntry],
    ) -> None:
        """Layout geometry is in the owner widget's coordinates, nested layouts included."""
        pending: List[Tuple[LayoutNode, NodeId]] = [(top, owner)]
        while pending:
            node, container = pending.pop()
            qlayout = self._realizer.layout_for(node.id)
            if qlayout is None:
                continue
            out.append(GeoEntry(node.id, "layout", _offset(qlayout.geometry(), x, y), container, True, _LAYOUT_Z))
            nested: List[Tuple[LayoutNode, NodeId]] = []
            for item in node.items:
                content = item.content
                if isinstance(content, WidgetNode):
                    holder[content.id] = node.id
                elif isinstance(content, LayoutNode):
                    nested.append((content, node.id))
                elif isinstance(content, SpacerNode):
                    spacer = self._realizer.spacer_for(content.id)
                    if spacer is not None:
                        rect = _offset(spacer.geometry(), x, y)
                        out.append(GeoEntry(content.id, "spacer", rect, node.id, True, _LAYOUT_Z))
            pending.extend(reversed(nested))

    def _titles(
        self,
        widget: QWidget,
        document: UiDocument,
        x: int,
        y: int,
        owner: NodeId,
        out: List[GeoEntry],
    ) -> None:
        if isinstance(widget, QTabWidget):
            bar = widget.tabBar()
            origin_x = x + bar.x()
            origin_y = y + bar.y()
            for index in range(widget.count()):
                page = _tagged_widget(widget.widget(index), document)
                if page is None:
                    continue
                rect = bar.tabRect(index)
                out.append(
                    GeoEntry(
                        page.id,
                        "page_tab",
                        Rect(
                            origin_x + rect.x(),
                            origin_y + rect.y(),
                            max(rect.width(), 1),
                            max(rect.height(), 1),
                        ),
                        owner,
                        True,
                        1000 + index,
                    )
                )
            return
        if not isinstance(widget, QToolBox):
            return
        buttons = [child for child in widget.children() if isinstance(child, QAbstractButton)]
        buttons.sort(key=lambda button: (button.y(), button.x()))
        for index, button in enumerate(buttons[: widget.count()]):
            page = _tagged_widget(widget.widget(index), document)
            if page is None:
                continue
            out.append(
                GeoEntry(
                    page.id,
                    "page_tab",
                    Rect(x + button.x(), y + button.y(), max(button.width(), 1), max(button.height(), 1)),
                    owner,
                    button.isVisible(),
                    1000 + index,
                )
            )


class HitIndexInvalidator:
    """Subscribed at PRIORITY_HIT_INDEX. Reads no geometry."""

    def __init__(self, index: HitIndex) -> None:
        self._index = index

    def on_changeset(self, changeset: ChangeSet) -> None:
        self._index.invalidate("changeset")


def survey_live(realizer: Realizer, index: HitIndex, document: UiDocument, scope: SurveyScope) -> Survey:
    """Measure ``scope`` and nothing else, in form coordinates. The caller made ``index`` fresh."""
    layouts = [_layout_facts(realizer, index, document, node) for node in scope.layouts]
    splitters = [_splitter_facts(realizer, index, node) for node in scope.splitters]
    return Survey(
        index.epoch,
        scope,
        _primary_facts(realizer, index, document, scope.primary),
        tuple(facts for facts in layouts if facts is not None),
        tuple(facts for facts in splitters if facts is not None),
    )


def _primary_facts(
    realizer: Realizer, index: HitIndex, document: UiDocument, primary: Optional[NodeId]
) -> Optional[PrimaryFacts]:
    if primary is None:
        return None
    node = document.get(primary)
    widget = realizer.widget_for(primary)
    rect = index.rect_of(primary)
    if not isinstance(node, WidgetNode) or widget is None or rect is None:
        return None
    free = free_origin(document, index, primary) if isinstance(positioning_of(document, primary), Free) else None
    return PrimaryFacts(primary, rect, class_default_policies(widget), free)


def _layout_facts(realizer: Realizer, index: HitIndex, document: UiDocument, layout_id: NodeId) -> Optional[LayoutFacts]:
    node = document.get(layout_id)
    qlayout = realizer.layout_for(layout_id)
    rect = index.rect_of(layout_id)
    if not isinstance(node, LayoutNode) or qlayout is None or rect is None:
        return None
    own = qlayout.geometry()
    # Items report geometry in the owner widget's coordinates, like the layout itself.
    dx = rect.x - own.x()
    dy = rect.y - own.y()
    margins = qlayout.contentsMargins()
    inner = qlayout.contentsRect()
    if isinstance(qlayout, QGridLayout):
        shape = grid_shape(document, layout_id)
        columns = tuple(_extent(qlayout.cellRect(0, column), dx, True) for column in range(shape.columns))
        rows = tuple(_extent(qlayout.cellRect(row, 0), dy, False) for row in range(shape.rows))
    elif node.class_name == "QFormLayout":
        columns, rows = _cell_tracks(realizer, document, grid_shape(document, layout_id), dx, dy)
    else:
        horizontal = node.class_name == "QHBoxLayout"
        tracks = _box_tracks(realizer, node, dx if horizontal else dy, horizontal)
        across = (_extent(inner, dy if horizontal else dx, not horizontal),)
        columns, rows = (tracks, across) if horizontal else (across, tracks)
    return LayoutFacts(
        layout_id,
        rect,
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
        columns,
        rows,
    )


def _box_tracks(realizer: Realizer, layout: LayoutNode, offset: int, horizontal: bool) -> Tuple[Track, ...]:
    found: List[Track] = []
    for item in layout.items:
        content = item.content
        geometry = _item_geometry(realizer, content)
        if content is None or geometry is None:
            continue
        found.append(_extent(geometry, offset, horizontal, content.id))
    # A right-to-left box lays its first item out last.
    found.sort(key=lambda track: track.start)
    return tuple(found)


def _cell_tracks(
    realizer: Realizer, document: UiDocument, shape: GridShape, dx: int, dy: int
) -> Tuple[Tuple[Track, ...], Tuple[Track, ...]]:
    """A form's label and field columns and its rows, from the items in them."""
    columns: Dict[int, Track] = {}
    rows: Dict[int, Track] = {}
    for cell in shape.cells:
        item = document.get(cell.item)
        geometry = _item_geometry(realizer, item.content) if isinstance(item, LayoutItemNode) else None
        if geometry is None:
            continue
        if cell.colspan == 1:
            columns[cell.column] = _union(columns.get(cell.column), _extent(geometry, dx, True))
        if cell.rowspan == 1:
            rows[cell.row] = _union(rows.get(cell.row), _extent(geometry, dy, False))
    return tuple(columns[at] for at in sorted(columns)), tuple(rows[at] for at in sorted(rows))


def _item_geometry(realizer: Realizer, content: Optional[Node]) -> Optional[QRect]:
    """None for an item Qt skips: a hidden widget or an empty layout."""
    if isinstance(content, WidgetNode):
        widget = realizer.widget_for(content.id)
        return None if widget is None or widget.isHidden() else widget.geometry()
    if isinstance(content, LayoutNode):
        qlayout = realizer.layout_for(content.id)
        return None if qlayout is None or qlayout.isEmpty() else qlayout.geometry()
    if isinstance(content, SpacerNode):
        spacer = realizer.spacer_for(content.id)
        return None if spacer is None else spacer.geometry()
    return None


def _splitter_facts(realizer: Realizer, index: HitIndex, splitter_id: NodeId) -> Optional[SplitterFacts]:
    splitter = realizer.widget_for(splitter_id)
    rect = index.rect_of(splitter_id)
    if not isinstance(splitter, QSplitter) or rect is None:
        return None
    horizontal = splitter.orientation() == Qt.Orientation.Horizontal
    inner = splitter.contentsRect()
    count = splitter.count()
    panes = [splitter.widget(at) for at in range(count)]
    return SplitterFacts(
        splitter_id,
        "h" if horizontal else "v",
        rect,
        inner.width() if horizontal else inner.height(),
        splitter.handleWidth(),
        # Handle 0 is never shown. Handle i sits before pane i.
        tuple(_offset(splitter.handle(at).geometry(), rect.x, rect.y) for at in range(1, count)),
        tuple(_offset(pane.geometry(), rect.x, rect.y) for pane in panes),
        tuple(int(size) for size in splitter.sizes()),
        tuple(_pane_minimum(pane, horizontal) for pane in panes),
    )


def _pane_minimum(pane: QWidget, horizontal: bool) -> int:
    stored = pane.minimumWidth() if horizontal else pane.minimumHeight()
    if stored > 0:
        return stored
    hint = pane.minimumSizeHint()
    return max(0, hint.width() if horizontal else hint.height())


def _extent(rect: QRect, offset: int, horizontal: bool, item: Optional[NodeId] = None) -> Track:
    if horizontal:
        return Track(offset + rect.x(), offset + rect.x() + rect.width(), item)
    return Track(offset + rect.y(), offset + rect.y() + rect.height(), item)


def _union(current: Optional[Track], extra: Track) -> Track:
    if current is None:
        return extra
    return Track(min(current.start, extra.start), max(current.end, extra.end))


def _tagged_widget(widget: QWidget, document: UiDocument) -> Optional[WidgetNode]:
    raw = widget.property(NODE_ID_PROPERTY)
    if raw is None or raw == "":
        return None
    node = document.get(NodeId(int(raw)))
    return node if isinstance(node, WidgetNode) else None


def _offset(rect: object, x: int, y: int) -> Rect:
    return Rect(x + rect.x(), y + rect.y(), rect.width(), rect.height())  # type: ignore[attr-defined]
