"""``GeometrySource`` over live widgets, and the ChangeSet invalidator (CONTRACTS.md section 5.5)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent
from app.qt.QtWidgets import QApplication, QWidget
from app.qt.qt_compat import enum_value
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.qtside.realize import NODE_ID_PROPERTY, Realizer

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


class HitIndexInvalidator:
    """Subscribed at PRIORITY_HIT_INDEX. Reads no geometry."""

    def __init__(self, index: HitIndex) -> None:
        self._index = index

    def on_changeset(self, changeset: ChangeSet) -> None:
        self._index.invalidate("changeset")


def _tagged_widget(widget: QWidget, document: UiDocument) -> Optional[WidgetNode]:
    raw = widget.property(NODE_ID_PROPERTY)
    if raw is None or raw == "":
        return None
    node = document.get(NodeId(int(raw)))
    return node if isinstance(node, WidgetNode) else None


def _offset(rect: object, x: int, y: int) -> Rect:
    return Rect(x + rect.x(), y + rect.y(), rect.width(), rect.height())  # type: ignore[attr-defined]
