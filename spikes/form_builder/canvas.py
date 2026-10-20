"""Live form canvas. Real widgets, a transparent overlay, and a cached hit index."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QLine, QMimeData, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.catalog import MIME, Entry
from spikes.form_builder.commands import (
    Compound,
    EnsureLayout,
    InsertItem,
    MoveItem,
    SetProperty,
    SetTabStops,
    resolve_layout_item,
)
from spikes.form_builder.model import (
    Widget,
    effective_tab_order,
    find_node,
    is_container,
    layout_items,
    make_item,
    make_layout,
    make_spacer,
    make_widget,
    prop_cstring,
    prop_enum,
    prop_set,
    prop_string,
    reading_order,
    set_attribute,
    tabstops_of,
    unique_name,
    widget_layout,
    widget_path,
)
from spikes.form_builder.realize import Realization
from spikes.form_builder.theme import tokens_for


class Overlay(QWidget):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.entries = []
        self.layout_info = {}
        self.selection = []
        self.slot = None
        self.mode = "widgets"
        self.tab_numbers = {}
        self.tokens = tokens_for("light")
        self.index_dirty = True
        self.mapper = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _rect(self, rect):
        if rect is None or self.mapper is None:
            return rect
        return self.mapper(rect)

    def _point(self, point):
        if self.mapper is None:
            return point
        return self.mapper(QRect(point, point)).topLeft()

    def paintEvent(self, _event):
        painter = QPainter(self)
        accent = QColor(self.tokens.accent)
        for info in self.layout_info.values():
            rect = self._rect(info["rect"])
            painter.setPen(QPen(QColor(self.tokens.border), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            chip = QRect(rect.left(), max(0, rect.top() - 14), 52, 14)
            painter.fillRect(chip, QColor(self.tokens.canvas))
            painter.setPen(QColor(self.tokens.muted))
            painter.drawText(chip, Qt.AlignCenter, info["label"])
            for _index, item_rect, kind in info["items"]:
                if kind != "spacer":
                    continue
                item_rect = self._rect(item_rect)
                painter.setPen(QPen(accent, 1, Qt.DotLine))
                painter.drawRect(item_rect.adjusted(1, 1, -2, -2))
                painter.drawText(item_rect, Qt.AlignCenter, "spacer")
        for node_id in self.selection:
            rect = self._rect(self.rect_for(node_id))
            if rect is None:
                continue
            painter.setPen(QPen(accent, self.tokens.focus + 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setBrush(accent)
            for handle in _handles(rect):
                painter.drawRect(handle)
        if self.slot is not None:
            painter.setPen(QPen(accent, 2))
            line = self.slot["line"]
            painter.drawLine(QLine(self._point(line.p1()), self._point(line.p2())))
            cell = self.slot.get("cell")
            if cell is not None:
                cell = self._rect(cell)
                painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 48))
                painter.drawRect(cell)
        if self.mode == "tab":
            for name, number in self.tab_numbers.items():
                rect = self._rect(self.rect_for_name(name))
                if rect is None:
                    continue
                badge = QRect(rect.left() - 2, rect.top() - 2, 18, 18)
                painter.setPen(Qt.NoPen)
                painter.setBrush(accent)
                painter.drawEllipse(badge)
                painter.setPen(QColor(self.tokens.accent_text))
                painter.drawText(badge, Qt.AlignCenter, str(number))
        painter.end()

    def rect_for(self, node_id: str):
        for rect, found, _kind in self.entries:
            if found == node_id:
                return rect
        info = self.layout_info.get(node_id)
        return None if info is None else info["rect"]

    def rect_for_name(self, name: str):
        surface = self.parent()
        realization = getattr(surface, "realization", None)
        if realization is None:
            return None
        for node_id, widget in realization.widgets.items():
            if widget.objectName() == name:
                return self.rect_for(node_id)
        return None

    def hit(self, pos: QPoint):
        widgets = [entry for entry in self.entries if entry[2] == "widget" and entry[0].contains(pos)]
        if widgets:
            widgets.sort(key=lambda entry: entry[0].width() * entry[0].height())
            return widgets[0]
        layouts = [entry for entry in self.entries if entry[2] == "layout" and entry[0].contains(pos)]
        if layouts:
            layouts.sort(key=lambda entry: entry[0].width() * entry[0].height())
            return layouts[0]
        return None

    def slot_at(self, pos: QPoint, doc):
        layouts = [entry for entry in self.entries if entry[2] == "layout" and entry[0].contains(pos)]
        if not layouts:
            hit = self.hit(pos)
            if hit is None or hit[2] != "widget":
                return None
            node = find_node(doc, hit[1])
            if isinstance(node, Widget) and is_container(node) and widget_layout(node) is None:
                return {
                    "layout_id": None,
                    "widget_id": node.id,
                    "index": 0,
                    "attrib": {},
                    "line": QLine(hit[0].left() + 6, hit[0].center().y(), hit[0].right() - 6, hit[0].center().y()),
                    "cell": hit[0],
                }
            return None
        layouts.sort(key=lambda entry: entry[0].width() * entry[0].height())
        layout_id = layouts[0][1]
        info = self.layout_info.get(layout_id)
        if info is None:
            return None
        return _slot_from_items(pos, layout_id, info)


def _handles(rect: QRect):
    size = 6
    points = [
        rect.topLeft(),
        QPoint(rect.center().x(), rect.top()),
        rect.topRight(),
        QPoint(rect.right(), rect.center().y()),
        rect.bottomRight(),
        QPoint(rect.center().x(), rect.bottom()),
        rect.bottomLeft(),
        QPoint(rect.left(), rect.center().y()),
    ]
    return [QRect(point.x() - size // 2, point.y() - size // 2, size, size) for point in points]


def _slot_from_items(pos: QPoint, layout_id: str, info: dict):
    kind = info["class"]
    rect = info["rect"]
    items = info["items"]
    if kind in {"QVBoxLayout", "QHBoxLayout"}:
        horizontal = kind == "QHBoxLayout"
        if not items:
            line = QLine(rect.left() + 6, rect.center().y(), rect.right() - 6, rect.center().y())
            return {"layout_id": layout_id, "widget_id": None, "index": 0, "attrib": {}, "line": line, "cell": None}
        for index, item_rect, _item_kind in items:
            midpoint = item_rect.center().x() if horizontal else item_rect.center().y()
            cursor = pos.x() if horizontal else pos.y()
            if cursor < midpoint:
                if horizontal:
                    line = QLine(item_rect.left(), item_rect.top(), item_rect.left(), item_rect.bottom())
                else:
                    line = QLine(item_rect.left(), item_rect.top(), item_rect.right(), item_rect.top())
                return {"layout_id": layout_id, "widget_id": None, "index": index, "attrib": {}, "line": line, "cell": None}
        last = items[-1][1]
        if horizontal:
            line = QLine(last.right(), last.top(), last.right(), last.bottom())
        else:
            line = QLine(last.left(), last.bottom(), last.right(), last.bottom())
        return {"layout_id": layout_id, "widget_id": None, "index": len(items), "attrib": {}, "line": line, "cell": None}
    if not items:
        line = QLine(rect.left() + 6, rect.center().y(), rect.right() - 6, rect.center().y())
        attrib = {"row": "0", "column": "0"} if kind == "QGridLayout" else {"row": "0", "column": "1"}
        return {"layout_id": layout_id, "widget_id": None, "index": 0, "attrib": attrib, "line": line, "cell": rect}
    nearest = min(items, key=lambda item: (item[1].center() - pos).manhattanLength())
    cell = nearest[1]
    if kind == "QFormLayout":
        column = "0" if pos.x() < rect.center().x() else "1"
        row = str(_row_index(items, pos.y()))
        line = QLine(rect.left() + 4, cell.top(), rect.right() - 4, cell.top())
        return {"layout_id": layout_id, "widget_id": None, "index": len(items), "attrib": {"row": row, "column": column}, "line": line, "cell": cell}
    row = str(_row_index(items, pos.y()))
    column = str(_col_index(items, pos.x()))
    line = QLine(cell.left(), cell.top(), cell.right(), cell.top())
    return {"layout_id": layout_id, "widget_id": None, "index": len(items), "attrib": {"row": row, "column": column}, "line": line, "cell": cell}


def _row_index(items, y: int) -> int:
    rows = sorted({item[1].top() for item in items})
    for index, top in enumerate(rows):
        if y < top + 8:
            return index
    return len(rows)


def _col_index(items, x: int) -> int:
    cols = sorted({item[1].left() for item in items})
    for index, left in enumerate(cols):
        if x < left + 8:
            return index
    return max(len(cols) - 1, 0)


class Surface(QGraphicsView):
    selected = Signal(list)
    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("canvasHost")
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.host = QWidget()
        self.host.setObjectName("canvasHost")
        self.margin = QVBoxLayout(self.host)
        self.margin.setContentsMargins(28, 28, 28, 28)
        self.page = QFrame()
        self.page.setObjectName("page")
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(8, 8, 8, 8)
        self.margin.addWidget(self.page)
        self.overlay = Overlay(self)
        self.proxy = self.scene().addWidget(self.host)
        self.realization = Realization()
        self.host.setProperty("realization", self.realization)
        self.doc = None
        self.history = None
        self.form = None
        self.scale_value = 1.0
        self.preview_width = 640
        self._press = None
        self._moving = None
        self.overlay.installEventFilter(self)
        self.overlay.mapper = self._to_view
        self.overlay.raise_()

    def refresh_overlay(self):
        self.overlay.update()
        self.proxy.update()
        self.viewport().update()

    def set_tokens(self, tokens):
        self.overlay.tokens = tokens
        self.refresh_overlay()

    def set_document(self, doc, history):
        self.doc = doc
        self.history = history
        self.rebuild()

    def rebuild(self):
        while self.page_layout.count():
            item = self.page_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if self.doc is None:
            return
        self.form = self.realization.build(self.doc)
        self.page_layout.addWidget(self.form)
        self.apply_width()
        QApplication.processEvents()
        self.rebuild_index()

    def apply_width(self):
        self.page.setFixedWidth(self.preview_width)
        self.host.adjustSize()
        self.host.resize(self.host.sizeHint().expandedTo(self.page.sizeHint() + QSize_pad()))
        self._place_overlay()
        self.scene().setSceneRect(self.proxy.boundingRect())

    def _place_overlay(self):
        self.overlay.setGeometry(self.viewport().geometry())
        self.overlay.raise_()

    def _to_view(self, rect: QRect) -> QRect:
        top_left = self.mapFromScene(self.proxy.mapToScene(rect.topLeft()))
        bottom_right = self.mapFromScene(self.proxy.mapToScene(rect.bottomRight()))
        return QRect(top_left, bottom_right).normalized()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()

    def set_scale(self, value: float):
        self.scale_value = value
        self.resetTransform()
        self.scale(value, value)

    def set_preview_width(self, width: int):
        self.preview_width = width
        self.apply_width()
        self.rebuild_index()

    def rebuild_index(self):
        self.overlay.entries = []
        self.overlay.layout_info = {}
        if self.form is None:
            return
        self._walk_widget(self.form)
        for layout_id, qlayout in list(self.realization.layouts.items()):
            parent = qlayout.parentWidget()
            if parent is None:
                continue
            geo = qlayout.geometry()
            origin = parent.mapTo(self.host, geo.topLeft())
            rect = QRect(origin, geo.size())
            if rect.width() < 28:
                rect.setWidth(28)
            if rect.height() < 28:
                rect.setHeight(28)
            items = []
            for index in range(qlayout.count()):
                item = qlayout.itemAt(index)
                item_geo = item.geometry()
                item_origin = parent.mapTo(self.host, item_geo.topLeft())
                item_rect = QRect(item_origin, item_geo.size())
                kind = "spacer" if item.widget() is None and item.layout() is None else "widget"
                items.append((index, item_rect, kind))
            label = {"QVBoxLayout": "VBOX", "QHBoxLayout": "HBOX", "QGridLayout": "GRID", "QFormLayout": "FORM"}.get(
                qlayout.metaObject().className(),
                qlayout.metaObject().className(),
            )
            self.overlay.layout_info[layout_id] = {
                "class": qlayout.metaObject().className(),
                "rect": rect,
                "items": items,
                "label": label,
            }
            self.overlay.entries.append((rect, layout_id, "layout"))
        self.overlay.index_dirty = False
        self.refresh_overlay()

    def _walk_widget(self, widget: QWidget):
        node_id = widget.property("formId")
        if node_id:
            origin = widget.mapTo(self.host, QPoint(0, 0))
            self.overlay.entries.append((QRect(origin, widget.size()), str(node_id), "widget"))
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if child.objectName().startswith("qt_"):
                for grand in child.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                    self._walk_widget(grand)
                continue
            self._walk_widget(child)

    def eventFilter(self, watched, event):
        if watched is not self.overlay or self.doc is None:
            return False
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press = self._overlay_host(event)
            self._moving = None
            return True
        if event.type() == QEvent.MouseMove and self._press is not None and self.overlay.mode == "widgets":
            pos = self._overlay_host(event)
            if (pos - self._press).manhattanLength() > 6:
                hit = self.overlay.hit(self._press)
                if hit and hit[2] == "widget":
                    self._moving = hit[1]
            if self._moving:
                if self.overlay.index_dirty:
                    self.rebuild_index()
                self.overlay.slot = self.overlay.slot_at(pos, self.doc)
                self.hovered.emit(self._slot_path(self.overlay.slot))
                self.refresh_overlay()
            return True
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            pos = self._overlay_host(event)
            if self._moving and self.overlay.slot is not None:
                self._commit_move(self._moving, self.overlay.slot)
            elif self.overlay.mode == "tab":
                self._tab_click(pos)
            elif self.overlay.mode == "buddy":
                self._buddy_click(pos)
            else:
                self._select_at(pos, event.modifiers())
            self._press = None
            self._moving = None
            self.overlay.slot = None
            self.refresh_overlay()
            return True
        return False

    def _select_at(self, pos, modifiers):
        if self.overlay.index_dirty:
            self.rebuild_index()
        hit = self.overlay.hit(pos)
        if hit is None:
            self.selected.emit([])
            return
        node_id = hit[1]
        if modifiers & (Qt.ShiftModifier | Qt.ControlModifier):
            current = list(self.overlay.selection)
            if node_id in current:
                current.remove(node_id)
            else:
                current.append(node_id)
            self.selected.emit(current)
            return
        self.selected.emit([node_id])

    def _tab_click(self, pos):
        hit = self.overlay.hit(pos)
        if hit is None or hit[2] != "widget" or self.history is None:
            return
        node = find_node(self.doc, hit[1])
        if not isinstance(node, Widget) or not node.object_name:
            return
        current = [name for name in effective_tab_order(self.doc) if name != node.object_name]
        current.append(node.object_name)
        self.history.execute(SetTabStops(current))

    def _buddy_click(self, pos):
        hit = self.overlay.hit(pos)
        if hit is None or hit[2] != "widget" or not self.overlay.selection or self.history is None:
            return
        source = find_node(self.doc, self.overlay.selection[0])
        target = find_node(self.doc, hit[1])
        if not isinstance(source, Widget) or source.class_name != "QLabel" or not isinstance(target, Widget):
            return
        self.history.execute(SetProperty(source.id, "buddy", prop_cstring("buddy", target.object_name)))

    def _commit_move(self, node_id, slot):
        item = resolve_layout_item(self.doc, node_id)
        if item is None or self.history is None:
            return
        if slot.get("layout_id"):
            self.history.execute(MoveItem(item.id, slot["layout_id"], slot["index"], slot.get("attrib") or None))
            return
        widget_id = slot.get("widget_id")
        if not widget_id:
            return
        layout_id = self.doc.alloc()
        self.history.execute(
            Compound(
                [
                    EnsureLayout(widget_id, "QVBoxLayout", layout_id, unique_name(self.doc, "verticalLayout")),
                    MoveItem(item.id, layout_id, 0, None),
                ]
            )
        )

    def _slot_path(self, slot) -> str:
        if not slot or self.doc is None:
            return ""
        node_id = slot.get("layout_id") or slot.get("widget_id")
        if not node_id:
            return ""
        return " / ".join(widget_path(self.doc, node_id))

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(MIME) or self.doc is None:
            event.ignore()
            return
        if self.overlay.index_dirty:
            self.rebuild_index()
        pos = self._host_pos(event.position().toPoint())
        self.overlay.slot = self.overlay.slot_at(pos, self.doc)
        self.hovered.emit(self._slot_path(self.overlay.slot))
        self.refresh_overlay()
        event.acceptProposedAction()

    def dropEvent(self, event):
        if self.doc is None or self.history is None:
            return
        raw = bytes(event.mimeData().data(MIME)).decode("utf-8")
        kind, class_name = raw.split(":", 1)
        entry = Entry(class_name, class_name, kind, "")
        pos = self._host_pos(event.position().toPoint())
        slot = self.overlay.slot or self.overlay.slot_at(pos, self.doc)
        if slot is not None:
            drop_entry(self.doc, self.history, entry, slot)
        self.overlay.slot = None
        self.refresh_overlay()
        event.acceptProposedAction()

    def dragLeaveEvent(self, _event):
        self.overlay.slot = None
        self.refresh_overlay()

    def _overlay_host(self, event) -> QPoint:
        view_pos = self.overlay.mapTo(self, event.position().toPoint())
        return self._host_pos(view_pos)

    def _host_pos(self, view_pos: QPoint) -> QPoint:
        return self.proxy.mapFromScene(self.mapToScene(view_pos)).toPoint()


def QSize_pad():
    from PySide6.QtCore import QSize

    return QSize(56, 56)


class Canvas(QWidget):
    selection_changed = Signal(list)
    status_text = Signal(str)
    timed = Signal(str, float)

    def __init__(self):
        super().__init__()
        self.primary = Surface()
        self.secondary = Surface()
        self.secondary.hide()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.primary)
        row.addWidget(self.secondary)
        self.two_widths = False
        self.doc = None
        self.history = None
        self.selection = []
        self.mode = "widgets"
        self.primary.selected.connect(self._on_selected)
        self.secondary.selected.connect(self._on_selected)
        self.primary.hovered.connect(self.status_text)

    def set_document(self, doc, history):
        started = time.perf_counter()
        self.doc = doc
        self.history = history
        self.primary.set_document(doc, history)
        if self.two_widths:
            self.secondary.set_document(doc, history)
        self.timed.emit("open", (time.perf_counter() - started) * 1000)
        self._sync_tab_badges()

    def on_command(self, command):
        started = time.perf_counter()
        if _is_structural(command) or self.primary.form is None:
            patched = self.primary.form is not None and self.primary.realization.sync()
            if patched:
                self.primary.overlay.index_dirty = True
                self.primary.apply_width()
                if self.two_widths:
                    self.secondary.realization.sync()
                    self.secondary.overlay.index_dirty = True
                    self.secondary.apply_width()
            else:
                self.primary.rebuild()
                if self.two_widths:
                    self.secondary.rebuild()
        else:
            _apply_light(self.primary, command)
            if self.two_widths:
                _apply_light(self.secondary, command)
            self.primary.rebuild_index()
        self.timed.emit("edit", (time.perf_counter() - started) * 1000)
        self._sync_tab_badges()
        self.primary.overlay.selection = list(self.selection)
        self.primary.refresh_overlay()

    def set_selection(self, ids):
        self.selection = list(ids)
        self.primary.overlay.selection = list(ids)
        self.secondary.overlay.selection = list(ids)
        self.primary.refresh_overlay()
        self.secondary.refresh_overlay()

    def set_mode(self, mode: str):
        self.mode = mode
        self.primary.overlay.mode = mode
        self.secondary.overlay.mode = mode
        self._sync_tab_badges()
        self.primary.refresh_overlay()

    def set_tokens(self, tokens):
        self.primary.set_tokens(tokens)
        self.secondary.set_tokens(tokens)

    def set_zoom(self, value: float):
        self.primary.set_scale(value)
        self.secondary.set_scale(value)

    def set_two_widths(self, enabled: bool):
        self.two_widths = enabled
        self.secondary.setVisible(enabled)
        if enabled and self.doc is not None:
            self.secondary.set_document(self.doc, self.history)
            self.primary.set_preview_width(420)
            self.secondary.set_preview_width(760)
        elif self.doc is not None:
            self.primary.set_preview_width(640)

    def set_width(self, width: int):
        self.primary.set_preview_width(width)

    def _on_selected(self, ids):
        self.set_selection(ids)
        self.selection_changed.emit(ids)

    def _sync_tab_badges(self):
        if self.doc is None:
            return
        order = reading_order(self.doc.root)
        stops = tabstops_of(self.doc)
        if stops and stops.names:
            order = list(stops.names)
        badges = {name: index + 1 for index, name in enumerate(order)}
        self.primary.overlay.tab_numbers = badges
        self.secondary.overlay.tab_numbers = badges


def _is_structural(command) -> bool:
    from spikes.form_builder.commands import Compound, Rename, SetAttribute, SetProperties, SetProperty, SetTabStops

    if isinstance(command, (SetProperty, SetProperties, Rename, SetAttribute, SetTabStops)):
        return False
    if isinstance(command, Compound):
        return any(_is_structural(step) for step in command.steps)
    return True


def _apply_light(surface: Surface, command) -> None:
    from spikes.form_builder.commands import Rename, SetAttribute, SetProperties, SetProperty

    if isinstance(command, SetProperty):
        surface.realization.apply_node_property(command.node_id, command.name)
    elif isinstance(command, SetProperties):
        for step in command.steps:
            surface.realization.apply_node_property(step.node_id, step.name)
    elif isinstance(command, Rename):
        node = find_node(surface.doc, command.node_id)
        widget = surface.realization.widgets.get(command.node_id)
        if isinstance(node, Widget) and widget is not None:
            widget.setObjectName(node.object_name)
    elif isinstance(command, SetAttribute):
        surface.rebuild()


def drop_entry(doc, history, entry: Entry, slot: dict) -> None:
    if entry.kind == "layout" and slot.get("widget_id"):
        target = find_node(doc, slot["widget_id"])
        if isinstance(target, Widget) and widget_layout(target) is None:
            history.execute(EnsureLayout(target.id, entry.class_name, doc.alloc(), unique_name(doc, "layout")))
            return
    content = content_for(doc, entry)
    if slot.get("layout_id") is None and slot.get("widget_id"):
        layout_id = doc.alloc()
        history.execute(
            Compound(
                [
                    EnsureLayout(slot["widget_id"], "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                    InsertItem(layout_id, 0, item_for(doc, content, slot.get("attrib") or {})),
                ]
            )
        )
        return
    if slot.get("layout_id"):
        history.execute(InsertItem(slot["layout_id"], slot["index"], item_for(doc, content, slot.get("attrib") or {})))
        return
    root_layout = widget_layout(doc.root)
    if root_layout is None:
        layout_id = doc.alloc()
        history.execute(
            Compound(
                [
                    EnsureLayout(doc.root.id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                    InsertItem(layout_id, 0, item_for(doc, content, {})),
                ]
            )
        )
        return
    history.execute(InsertItem(root_layout.id, len(layout_items(root_layout)), item_for(doc, content, {})))


def content_for(doc, entry: Entry):
    if entry.kind == "spacer":
        return make_spacer(doc, entry.class_name)
    if entry.kind == "layout":
        host = make_widget(doc, "QWidget")
        host.body.append(make_layout(doc, entry.class_name))
        return host
    widget = make_widget(doc, entry.class_name)
    if entry.class_name == "QLabel":
        widget.body.append(prop_string("text", "Label"))
    elif entry.class_name in {"QPushButton", "QToolButton", "QCheckBox", "QRadioButton"}:
        widget.body.append(prop_string("text", widget.object_name))
    elif entry.class_name == "QGroupBox":
        widget.body.append(prop_string("title", "Group"))
    elif entry.class_name == "QTabWidget":
        page = make_widget(doc, "QWidget", unique_name(doc, "page"))
        set_attribute(page, "title", "Page 1")
        page.body.append(make_layout(doc, "QVBoxLayout"))
        widget.body.append(page)
    elif entry.class_name == "QSplitter":
        widget.body.append(prop_enum("orientation", "Qt::Horizontal"))
    elif entry.class_name == "QDialogButtonBox":
        widget.body.append(prop_set("standardButtons", "QDialogButtonBox::Cancel|QDialogButtonBox::Ok"))
    return widget


def item_for(doc, content, attrib: dict):
    return make_item(doc, content, **attrib)


def start_drag(widget: QWidget, entry: Entry) -> None:
    mime = QMimeData()
    mime.setData(MIME, f"{entry.kind}:{entry.class_name}".encode("utf-8"))
    drag = QDrag(widget)
    drag.setMimeData(mime)
    drag.exec(Qt.CopyAction)
