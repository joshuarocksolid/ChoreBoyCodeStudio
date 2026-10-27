"""``GeometrySource`` over live widgets, and the ChangeSet invalidator (CONTRACTS.md section 5.5)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QRect, Qt
from app.qt.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDockWidget,
    QGridLayout,
    QGroupBox,
    QSplitter,
    QTabWidget,
    QToolBox,
    QWidget,
)
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
from app.features.form_builder.engine.query.hit_index import (
    GeoEntry,
    HitIndex,
    IndexPatch,
    Rect,
    RefreshScope,
)
from app.features.form_builder.engine.query.tree import grid_shape
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.qtside.canvas.core.structure import (
    Free,
    LaidOut,
    Managed,
    free_origin,
    positioning_of,
)
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

    def retouch(self, previous: Sequence[GeoEntry], scope: RefreshScope) -> Optional[IndexPatch]:
        """O(changed + dependants). None means the caller walks the whole form.

        A property edit reads each dirty widget. Layout siblings and ancestors
        are read only after a rect actually moves. Added or removed nodes are
        patched when they are leaves. A moved container falls back to the full walk.
        """
        if scope.full:
            return None
        root = self._realizer.root_widget
        document = self._realizer.document
        root_node = document.root
        if root is None or not isinstance(root_node, WidgetNode) or not previous:
            return None
        self.settle()
        slots: Dict[Tuple[NodeId, str], List[int]] = {}
        for index, entry in enumerate(previous):
            slots.setdefault((entry.node, entry.kind), []).append(index)
        queue: List[NodeId] = []
        for node_id in list(scope.dirty) + list(scope.added):
            if node_id not in scope.removed and node_id not in queue:
                queue.append(node_id)
        seen: Dict[NodeId, bool] = {}
        replacements: List[Tuple[int, GeoEntry]] = []
        extra: List[GeoEntry] = []
        changed: List[NodeId] = []
        visits = 0
        while queue:
            node_id = queue.pop()
            if node_id in seen or node_id in scope.removed:
                continue
            seen[node_id] = True
            found = document.get(node_id)
            if found is None or not isinstance(found, (WidgetNode, LayoutNode, SpacerNode)):
                continue
            measured = self._measure(found, root)
            if measured is None:
                return None
            rect, visible = measured
            visits += 1
            kind = "widget" if isinstance(found, WidgetNode) else "layout" if isinstance(found, LayoutNode) else "spacer"
            indexes = slots.get((node_id, kind), [])
            if not indexes:
                if node_id not in scope.added:
                    return None
                made = self._new_entry(found, rect, visible, document)
                if made is None:
                    return None
                extra.append(made)
                changed.append(node_id)
                if _container_moved(found, None, rect):
                    return None
                queue.extend(_dependants(document, node_id))
                continue
            old = previous[indexes[0]]
            if old.rect == rect and old.visible == visible:
                continue
            updated = GeoEntry(old.node, old.kind, rect, old.container, visible, old.z)
            replacements.append((indexes[0], updated))
            changed.append(node_id)
            if old.rect != rect:
                if _container_moved(found, old.rect, rect):
                    return None
                if (
                    slots.get((node_id, "page_tab"))
                    or slots.get((node_id, "menu_title"))
                    or slots.get((node_id, "title_band"))
                ):
                    return None
                queue.extend(_dependants(document, node_id))
        if not replacements and not extra and not scope.removed:
            return IndexPatch(visits=visits, changed=())
        return IndexPatch(
            replacements=tuple(replacements),
            extra=tuple(extra),
            drop=scope.removed,
            visits=visits,
            changed=tuple(changed),
        )

    def _measure(self, node: object, root: QWidget) -> Optional[Tuple[Rect, bool]]:
        """One entry's form rect. O(depth) parent hops, not a tree walk."""
        if isinstance(node, WidgetNode):
            widget = self._realizer.widget_for(node.id)
            if not isinstance(widget, QWidget):
                return None
            return _form_rect(widget, root), bool(widget.isVisible())
        if isinstance(node, LayoutNode):
            qlayout = self._realizer.layout_for(node.id)
            if qlayout is None:
                return None
            origin = _owner_origin(self._realizer, node, root)
            if origin is None:
                return None
            return _offset(qlayout.geometry(), origin[0], origin[1]), True
        if isinstance(node, SpacerNode):
            spacer = self._realizer.spacer_for(node.id)
            if spacer is None:
                return None
            origin = _owner_origin(self._realizer, node, root)
            if origin is None:
                return None
            return _offset(spacer.geometry(), origin[0], origin[1]), True
        return None

    def _new_entry(
        self,
        node: object,
        rect: Rect,
        visible: bool,
        document: UiDocument,
    ) -> Optional[GeoEntry]:
        """O(siblings of the Qt parent) to read z. Used when a ChangeSet added a leaf."""
        if not isinstance(node, (WidgetNode, LayoutNode, SpacerNode)):
            return None
        place = positioning_of(document, node.id)
        if isinstance(place, LaidOut):
            container: Optional[NodeId] = place.layout
        elif isinstance(place, Free):
            container = place.parent
        elif isinstance(place, Managed):
            container = place.container
        else:
            container = None
        if isinstance(node, WidgetNode):
            widget = self._realizer.widget_for(node.id)
            if not isinstance(widget, QWidget):
                return None
            return GeoEntry(node.id, "widget", rect, container, visible, _z_of(widget))
        if isinstance(node, LayoutNode):
            return GeoEntry(node.id, "layout", rect, container, True, _LAYOUT_Z)
        return GeoEntry(node.id, "spacer", rect, container, True, _LAYOUT_Z)

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
        if isinstance(widget, QToolBox):
            _toolbox_titles(widget, document, x, y, owner, out)
            return
        band = _title_band(widget)
        if band is None:
            return
        out.append(GeoEntry(owner, "title_band", Rect(x + band.x, y + band.y, band.width, band.height), owner, True, 900))


def _toolbox_titles(
    widget: QToolBox,
    document: UiDocument,
    x: int,
    y: int,
    owner: NodeId,
    out: List[GeoEntry],
) -> None:
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


def _title_band(widget: QWidget) -> Optional[Rect]:
    """The title strip in widget-local pixels. None when the widget has no strip."""
    if isinstance(widget, QGroupBox):
        top = int(widget.contentsRect().top())
        if top <= 0:
            return None
        return Rect(0, 0, max(widget.width(), 1), top)
    if isinstance(widget, QDockWidget):
        bar = widget.titleBarWidget()
        if bar is not None and bar.isVisible() and bar.height() > 0:
            return Rect(bar.x(), bar.y(), max(bar.width(), 1), bar.height())
        top = int(widget.contentsRect().top())
        if top <= 0:
            return None
        return Rect(0, 0, max(widget.width(), 1), top)
    return None


class HitIndexInvalidator:
    """Subscribed at PRIORITY_HIT_INDEX. Reads no geometry."""

    def __init__(self, index: HitIndex) -> None:
        self._index = index

    def on_changeset(self, changeset: ChangeSet) -> None:
        """O(changed). Records the stale ids. Geometry is read later, on refresh."""
        if changeset.replaced:
            self._index.invalidate("changeset")
            return
        dirty = set(changeset.structure_dirty)
        dirty.update(changeset.added)
        for owner, _kind, _name in changeset.property_dirty:
            dirty.add(owner)
        for change in changeset.changes:
            for name in ("node", "owner", "parent", "old_parent", "new_parent"):
                node_id = getattr(change, name, None)
                if node_id is not None:
                    dirty.add(node_id)
        self._index.invalidate(
            "changeset",
            RefreshScope(
                dirty=frozenset(node_id for node_id in dirty if node_id not in changeset.removed),
                removed=changeset.removed,
                added=changeset.added,
            ),
        )


def survey_live(
    realizer: Realizer,
    index: HitIndex,
    document: UiDocument,
    scope: SurveyScope,
    previous: Optional[Survey] = None,
) -> Survey:
    """Measure ``scope`` and nothing else, in form coordinates. The caller made ``index`` fresh.

    ``previous`` lends its layouts and splitters when the epoch and those scopes match,
    so moving the selection between siblings measures only the new primary.
    """
    primary = _primary_facts(realizer, index, document, scope.primary)
    if (
        previous is not None
        and previous.epoch == index.epoch
        and previous.scope.layouts == scope.layouts
        and previous.scope.splitters == scope.splitters
    ):
        return Survey(index.epoch, scope, primary, previous.layouts, previous.splitters)
    layouts = [_layout_facts(realizer, index, document, node) for node in scope.layouts]
    splitters = [_splitter_facts(realizer, index, node) for node in scope.splitters]
    return Survey(
        index.epoch,
        scope,
        primary,
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
    # Cell and contents rects are in the owner widget's coordinates, like the layout itself.
    dx = rect.x - own.x()
    dy = rect.y - own.y()
    margins = qlayout.contentsMargins()
    inner = qlayout.contentsRect()
    if isinstance(qlayout, QGridLayout):
        shape = grid_shape(document, layout_id)
        columns = tuple(_extent(qlayout.cellRect(0, column), dx, True) for column in range(shape.columns))
        rows = tuple(_extent(qlayout.cellRect(row, 0), dy, False) for row in range(shape.rows))
    elif node.class_name == "QFormLayout":
        columns, rows = _form_tracks(_shown_items(realizer, index, node))
    else:
        horizontal = node.class_name == "QHBoxLayout"
        tracks = _box_tracks(_shown_items(realizer, index, node), horizontal)
        across = (_extent(inner, dy if horizontal else dx, not horizontal),)
        columns, rows = (tracks, across) if horizontal else (across, tracks)
    box_spacing = int(qlayout.spacing()) if hasattr(qlayout, "spacing") else None
    horizontal = int(qlayout.horizontalSpacing()) if hasattr(qlayout, "horizontalSpacing") else None
    vertical = int(qlayout.verticalSpacing()) if hasattr(qlayout, "verticalSpacing") else None
    return LayoutFacts(
        layout_id,
        rect,
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
        columns,
        rows,
        box_spacing,
        horizontal,
        vertical,
    )


def _shown_items(realizer: Realizer, index: HitIndex, layout: LayoutNode) -> List[Tuple[LayoutItemNode, NodeId, Rect]]:
    """``layout``'s items that Qt gives space to, with their rects from ``index``.

    A hidden widget and an empty layout get none.
    """
    rects = {entry.node: entry.rect for entry in index.children_of(layout.id) if entry.visible}
    found: List[Tuple[LayoutItemNode, NodeId, Rect]] = []
    for item in layout.items:
        content = item.content
        rect = None if content is None else rects.get(content.id)
        if content is None or rect is None:
            continue
        if isinstance(content, LayoutNode):
            qlayout = realizer.layout_for(content.id)
            if qlayout is None or qlayout.isEmpty():
                continue
        found.append((item, content.id, rect))
    return found


def _box_tracks(shown: Sequence[Tuple[LayoutItemNode, NodeId, Rect]], horizontal: bool) -> Tuple[Track, ...]:
    found = [_along(rect, horizontal, content) for _item, content, rect in shown]
    # A right-to-left box lays its first item out last.
    found.sort(key=lambda track: track.start)
    return tuple(found)


def _form_tracks(shown: Sequence[Tuple[LayoutItemNode, NodeId, Rect]]) -> Tuple[Tuple[Track, ...], Tuple[Track, ...]]:
    """A form's label and field columns and its rows, from the items in them. A spanning item is in no column."""
    columns: Dict[int, List[int]] = {}
    rows: Dict[int, List[int]] = {}
    for item, _content, rect in shown:
        if (item.colspan or 1) == 1:
            _grow(columns, item.column or 0, rect.x, rect.x + rect.width)
        if (item.rowspan or 1) == 1:
            _grow(rows, item.row or 0, rect.y, rect.y + rect.height)
    return _tracks(columns), _tracks(rows)


def _grow(spans: Dict[int, List[int]], at: int, start: int, end: int) -> None:
    span = spans.get(at)
    if span is None:
        spans[at] = [start, end]
        return
    span[0] = min(span[0], start)
    span[1] = max(span[1], end)


def _tracks(spans: Dict[int, List[int]]) -> Tuple[Track, ...]:
    return tuple(Track(spans[at][0], spans[at][1]) for at in sorted(spans))


def _along(rect: Rect, horizontal: bool, item: Optional[NodeId] = None) -> Track:
    if horizontal:
        return Track(rect.x, rect.x + rect.width, item)
    return Track(rect.y, rect.y + rect.height, item)


def _splitter_facts(realizer: Realizer, index: HitIndex, splitter_id: NodeId) -> Optional[SplitterFacts]:
    found = realizer.widget_for(splitter_id)
    rect = index.rect_of(splitter_id)
    if rect is None or found is None or not isinstance(found, QSplitter):
        return None
    splitter = found
    horizontal = splitter.orientation() == Qt.Orientation.Horizontal
    inner = splitter.contentsRect()
    count = splitter.count()
    panes: List[QWidget] = []
    for at in range(count):
        pane = splitter.widget(at)
        if not isinstance(pane, QWidget):
            return None
        panes.append(pane)
    handles: List[Rect] = []
    for at in range(1, count):
        handle = splitter.handle(at)
        if handle is None:
            return None
        handles.append(_offset(handle.geometry(), rect.x, rect.y))
    return SplitterFacts(
        splitter_id,
        "h" if horizontal else "v",
        rect,
        inner.width() if horizontal else inner.height(),
        splitter.handleWidth(),
        # Handle 0 is never shown. Handle i sits before pane i.
        tuple(handles),
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


def _form_rect(widget: QWidget, root: QWidget) -> Rect:
    """Form coordinates. O(depth) parent hops."""
    if widget is root:
        return Rect(0, 0, widget.width(), widget.height())
    x, y = _origin(widget, root)
    return Rect(x, y, widget.width(), widget.height())


def _origin(widget: QWidget, root: QWidget) -> Tuple[int, int]:
    x = 0
    y = 0
    current: Optional[QWidget] = widget
    guard = 0
    while current is not None and current is not root and guard < 64:
        x += current.x()
        y += current.y()
        parent = current.parentWidget()
        current = parent if isinstance(parent, QWidget) else None
        guard += 1
    return x, y


def _owner_origin(realizer: Realizer, node: object, root: QWidget) -> Optional[Tuple[int, int]]:
    """The owner widget's form origin. Layout geometry is in that widget's coordinates."""
    current = node
    while current is not None:
        if isinstance(current, LayoutNode):
            owner_id = current.owner_widget_id()
            if owner_id is not None:
                widget = realizer.widget_for(owner_id)
                if not isinstance(widget, QWidget):
                    return None
                if widget is root:
                    return (0, 0)
                return _origin(widget, root)
        parent_id = getattr(current, "parent_id", None)
        current = realizer.document.get(parent_id) if parent_id is not None else None
    return (0, 0)


def _z_of(widget: QWidget) -> int:
    """O(siblings). The index among the Qt parent's children, which is paint order."""
    parent = widget.parent()
    if parent is None:
        return 0
    for index, child in enumerate(parent.children()):
        if child is widget:
            return index
    return 0


def _container_moved(node: object, old: Optional[Rect], new: Rect) -> bool:
    """A container whose origin or size moved makes every descendant stale."""
    if isinstance(node, WidgetNode) and (node.child_widgets or node.layout is not None):
        if old is None:
            return True
        return old != new
    if isinstance(node, LayoutNode) and old is not None and old != new:
        return any(item.content is not None for item in node.items)
    return False


def _dependants(document: UiDocument, node_id: NodeId) -> List[NodeId]:
    """Siblings in the same layout, plus ancestors. O(siblings + depth)."""
    found: List[NodeId] = []
    place = positioning_of(document, node_id)
    if isinstance(place, LaidOut):
        found.append(place.layout)
        layout = document.get(place.layout)
        if isinstance(layout, LayoutNode):
            for item in layout.items:
                content = item.content
                if content is not None and content.id != node_id:
                    found.append(content.id)
    elif isinstance(place, Free):
        found.append(place.parent)
    elif isinstance(place, Managed):
        found.append(place.container)
    found.extend(document.ancestors(node_id))
    return found


def _tagged_widget(widget: QWidget, document: UiDocument) -> Optional[WidgetNode]:
    raw = widget.property(NODE_ID_PROPERTY)
    if raw is None or raw == "":
        return None
    node = document.get(NodeId(int(raw)))
    return node if isinstance(node, WidgetNode) else None


def _offset(rect: object, x: int, y: int) -> Rect:
    return Rect(x + rect.x(), y + rect.y(), rect.width(), rect.height())  # type: ignore[attr-defined]
