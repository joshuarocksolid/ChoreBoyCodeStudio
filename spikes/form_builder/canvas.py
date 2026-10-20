"""Live form canvas: real widgets in a graphics view, a painted overlay, a cached hit index.

Layers, bottom to top: the dot-grid backdrop, the page card with the real form,
then one transparent overlay that paints layout frames, gaps and margins, hover,
selection, drop indicators, mode badges and banners. All pointer work during a
drag is hit-testing the cached index; every edit is a command.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from PySide6 import QtWidgets
from PySide6.QtCore import QEvent, QLineF, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QColor, QCursor, QDrag, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder import sizing
from spikes.form_builder.catalog import MIME, Entry
from spikes.form_builder.commands import (
    Compound,
    EnsureLayout,
    InsertChild,
    InsertItem,
    InsertPart,
    MoveItem,
    SetItemAttrib,
    SetProperty,
    SetTabStops,
    resolve_layout_item,
    with_tab_splice,
)
from spikes.form_builder.icons import paint_glyph
from spikes.form_builder.kit import chip, paint_shadow, qcolor
from spikes.form_builder.model import (
    INPUT_CLASSES,
    Action,
    ActionRef,
    Layout,
    LayoutItem,
    Spacer,
    Widget,
    child_widgets,
    clone_widget,
    effective_tab_order,
    find_node,
    get_property,
    is_container,
    item_content,
    iter_nodes,
    layout_items,
    locate,
    make_item,
    make_layout,
    make_spacer,
    make_widget,
    prop_cstring,
    prop_enum,
    prop_rect,
    prop_set,
    prop_string,
    reading_order,
    set_attribute,
    tabstops_of,
    unique_name,
    widget_layout,
)
from spikes.form_builder.realize import PAGE_CLASSES, Realization, form_rows, widget_class
from spikes.form_builder.theme import current, runtime_font, runtime_palette, tokens_for

TITLE_STRIP = 30
LAYOUT_WORDS = {"QVBoxLayout": "VBox", "QHBoxLayout": "HBox", "QGridLayout": "Grid", "QFormLayout": "Form", "QSplitter": "Splitter"}
LAYOUT_NAMES = {
    "QVBoxLayout": "vertical layout",
    "QHBoxLayout": "horizontal layout",
    "QGridLayout": "grid",
    "QFormLayout": "form layout",
    "QSplitter": "splitter",
}
MIN_TARGET = 32
_DEFAULTS: dict[str, tuple[str, str]] = {}


def class_default(doc, class_name: str) -> tuple[str, str]:
    """The size policy a class starts with, read once from a real instance."""
    if class_name not in _DEFAULTS:
        cls, _custom = widget_class(doc, class_name)
        try:
            probe = cls()
            policy = probe.sizePolicy()
            _DEFAULTS[class_name] = (policy.horizontalPolicy().name, policy.verticalPolicy().name)
            probe.deleteLater()
        except Exception:  # noqa: BLE001 - an odd custom base must not break the canvas
            _DEFAULTS[class_name] = ("Preferred", "Preferred")
    return _DEFAULTS[class_name]


# --------------------------------------------------------------------------- index
@dataclass
class ItemGeo:
    content_id: str
    item_id: str
    rect: QRect
    kind: str
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1


@dataclass
class LayoutGeo:
    id: str
    cls: str
    rect: QRect
    content: QRect
    owner_id: str
    items: list = field(default_factory=list)
    spacing: int = 6
    hspacing: int = 6
    vspacing: int = 6
    margins: tuple = (0, 0, 0, 0)
    vertical: bool = True
    cells: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    label_right: int = 0
    field_left: int = 0


@dataclass
class GeoIndex:
    hits: list = field(default_factory=list)
    rect_of: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    layouts: dict = field(default_factory=dict)
    layout_of_owner: dict = field(default_factory=dict)
    page: QRect = field(default_factory=QRect)
    form: QRect = field(default_factory=QRect)
    menubar: tuple | None = None


@dataclass
class Slot:
    mode: str
    layout_id: str = ""
    index: int = 0
    attrib: dict = field(default_factory=dict)
    widget_id: str = ""
    target: QRect = field(default_factory=QRect)
    line: QLineF | None = None
    cell: QRect | None = None
    label: str = ""
    new_row: int = -1


# --------------------------------------------------------------------------- page
class PageFrame(QFrame):
    """The window card: soft shadow, rounded corners, a mini title bar with windowTitle."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, _event):
        tokens = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        paint_shadow(painter, rect, 10, strength=26 if not tokens.dark else 60)
        palette = runtime_palette()
        painter.setPen(QPen(QColor(0, 0, 0, 40 if not tokens.dark else 120), 1))
        painter.setBrush(palette.window().color())
        painter.drawRoundedRect(rect, 10, 10)
        strip = QRectF(rect.left(), rect.top(), rect.width(), TITLE_STRIP)
        path = QPainterPath()
        path.addRoundedRect(strip, 10, 10)
        path.addRect(QRectF(strip.left(), strip.top() + 12, strip.width(), strip.height() - 12))
        painter.setPen(Qt.NoPen)
        painter.setBrush(palette.window().color().darker(106))
        painter.drawPath(path.simplified())
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        painter.drawLine(QPointF(strip.left(), strip.bottom()), QPointF(strip.right(), strip.bottom()))
        controls = QPen(QColor(110, 110, 110), 1.2)
        painter.setPen(controls)
        cy = strip.center().y()
        right = strip.right() - 14
        painter.drawLine(QPointF(right - 4, cy - 4), QPointF(right + 4, cy + 4))
        painter.drawLine(QPointF(right + 4, cy - 4), QPointF(right - 4, cy + 4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(right - 26, cy - 4, 8, 8))
        painter.drawLine(QPointF(right - 48, cy + 3), QPointF(right - 40, cy + 3))
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(strip, Qt.AlignCenter, self.title or "Untitled")
        painter.end()


# --------------------------------------------------------------------------- overlay
class Overlay(QWidget):
    """Transparent, on top of the view. Paints everything that is not a real widget."""

    def __init__(self, surface):
        super().__init__(surface)
        self.surface = surface
        self.hover = None
        self.selection: list[str] = []
        self.slot: Slot | None = None
        self.mode = "design"
        self.tab_numbers: dict[str, int] = {}
        self.tab_next = 1
        self.buddy_drag: tuple | None = None
        self.gap_hover = None
        self.drag_label = ""
        self.cursor_pos = QPoint()
        self.menu_open: str = ""
        self.menu_rows: list = []
        self.header = ""
        self.tokens = tokens_for("light")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    # entries kept for older callers
    @property
    def entries(self):
        return self.surface.index.hits

    @property
    def layout_info(self):
        return self.surface.index.layouts

    def paintEvent(self, _event):
        surface = self.surface
        if surface.doc is None:
            return
        if surface.index_dirty:
            surface.rebuild_index()
        tokens = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        index = surface.index
        self._paint_page_chrome(painter, tokens, index)
        self._paint_layouts(painter, tokens, index)
        if self.mode == "design":
            self._paint_details(painter, tokens, index)
            self._paint_hover(painter, tokens, index)
            self._paint_selection(painter, tokens, index)
            self._paint_menu(painter, tokens, index)
            self._paint_slot(painter, tokens)
        elif self.mode == "tab":
            self._paint_tabs(painter, tokens, index)
        elif self.mode == "buddy":
            self._paint_buddies(painter, tokens, index)
        self._paint_banner(painter, tokens)
        painter.end()

    # -- helpers
    def v(self, rect) -> QRectF:
        return self.surface.to_view(rect)

    def vp(self, point) -> QPointF:
        return self.surface.to_view_point(point)

    # -- page
    def _paint_page_chrome(self, p, t, index):
        if index.page.isNull():
            return
        page = self.v(index.page.adjusted(8, 8, -8, -8))
        form = self.v(index.form)
        doc = self.surface.doc
        width, height = self.surface.form_size()
        text = f"{width} × {height}"
        hint = self.surface.content_min()
        if hint and (hint[0] > width or hint[1] > height):
            text += f"   ·   content needs {hint[0]} × {hint[1]}"
        font = QFont(QGuiApplication.font())
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor(t.faint))
        p.drawText(QRectF(page.left(), page.bottom() + 8, page.width(), 16), Qt.AlignHCenter | Qt.AlignTop, text)
        if self.header:
            chip(p, QPointF(page.left(), page.top() - 8), self.header, t.surface, t.muted, glyph="width", bold=False)
        # Resize grips on the right and bottom edges.
        p.setPen(Qt.NoPen)
        p.setBrush(qcolor(t.faint, 150))
        p.drawRoundedRect(QRectF(page.right() + 4, page.center().y() - 14, 4, 28), 2, 2)
        p.drawRoundedRect(QRectF(page.center().x() - 14, page.bottom() + 4 + 20, 28, 4), 2, 2)
        if doc is not None and self.mode == "design" and self._form_is_empty():
            box = form.adjusted(24, 24, -24, -24)
            if box.height() > 120:
                box.setHeight(min(box.height(), 160))
            pen = QPen(qcolor(t.accent, 140), 1.5, Qt.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.setBrush(qcolor(t.accent, 14))
            p.drawRoundedRect(box, 10, 10)
            paint_glyph(p, "plus", QRectF(box.center().x() - 10, box.center().y() - 30, 20, 20), t.accent)
            font.setPixelSize(13)
            font.setWeight(QFont.DemiBold)
            p.setFont(font)
            p.setPen(QColor("#33363d"))
            p.drawText(QRectF(box.left(), box.center().y() - 4, box.width(), 18), Qt.AlignCenter, "Drop a widget here")
            font.setWeight(QFont.Normal)
            font.setPixelSize(12)
            p.setFont(font)
            p.setPen(QColor("#6b7280"))
            p.drawText(QRectF(box.left(), box.center().y() + 16, box.width(), 18), Qt.AlignCenter, "or press / to insert one. It lands in a layout, so it resizes with the window.")

    def _form_is_empty(self) -> bool:
        doc = self.surface.doc
        if doc.root.class_name == "QMainWindow":
            return False
        layout = widget_layout(doc.root)
        if layout is None:
            return not child_widgets(doc.root)
        return not layout_items(layout)

    # -- layouts
    def _focus_layouts(self, index) -> set:
        focus = set()
        ids = list(self.selection)
        if self.hover:
            ids.append(self.hover)
        for node_id in ids:
            if node_id in index.layouts:
                focus.add(node_id)
            owned = index.layout_of_owner.get(node_id)
            if owned:
                focus.add(owned)
            parent = self.surface.parent_layout_id(node_id)
            if parent:
                focus.add(parent)
        if self.slot is not None and self.slot.layout_id:
            focus.add(self.slot.layout_id)
        return focus

    def _paint_layouts(self, p, t, index):
        focus = self._focus_layouts(index) if self.mode == "design" else set()
        font = QFont(QGuiApplication.font())
        font.setPixelSize(10)
        font.setWeight(QFont.DemiBold)
        for layout_id, geo in index.layouts.items():
            rect = self.v(geo.rect).adjusted(0.5, 0.5, -0.5, -0.5)
            strong = layout_id in focus
            if self.mode != "design" and not geo.items:
                continue
            pen = QPen(qcolor(t.layout, 200 if strong else 70), 1, Qt.SolidLine if strong else Qt.DashLine)
            if not strong:
                pen.setDashPattern([3, 3])
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 3, 3)
            if not geo.items and self.mode == "design" and not (geo.owner_id == self.surface.doc.root.id):
                fill = QRectF(rect).adjusted(3, 3, -3, -3)
                p.setPen(Qt.NoPen)
                p.setBrush(qcolor(t.layout, 18))
                p.drawRoundedRect(fill, 3, 3)
                p.setFont(font)
                p.setPen(qcolor(t.layout, 220))
                p.drawText(fill, Qt.AlignCenter, "Drop widgets here")
            if self.mode == "design":
                for item in geo.items:
                    if item.kind == "spacer":
                        self._paint_spring(p, t, self.v(item.rect), strong or item.content_id in self.selection)
            if strong:
                words = LAYOUT_WORDS.get(geo.cls, geo.cls)
                if geo.cls == "QGridLayout" and geo.cells:
                    rows = max(cell[0] for cell in geo.cells) + 1
                    cols = max(cell[1] for cell in geo.cells) + 1
                    words += f" {rows}×{cols}"
                if geo.owner_id == self.surface.doc.root.id:
                    anchor = QPointF(self.v(index.page.adjusted(8, 8, -8, -8)).left(), self.v(index.page).top() + 6)
                    chip(p, anchor, "Window · " + words, t.layout, "#FFFFFF", glyph=geo.cls, pixel_size=10)
                else:
                    # Top-right: titles and labels sit top-left, so the chip stays out of their way.
                    chip(p, QPointF(rect.right() + 0.5, rect.top() + 1), words, t.layout, "#FFFFFF", align="right", glyph=geo.cls, pixel_size=10)

    def _paint_spring(self, p, t, rect: QRectF, strong: bool):
        """Spacers are drawn as springs, the way Designer users expect to find them."""
        horizontal = rect.width() >= rect.height()
        length = (rect.width() if horizontal else rect.height()) - 8
        if length < 12:
            return
        p.save()
        p.translate(rect.center())
        if not horizontal:
            p.rotate(90)
        half = length / 2
        pen = QPen(qcolor(t.gap, 220 if strong else 120), 1.25)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(-half, -4), QPointF(-half, 4))
        p.drawLine(QPointF(half, -4), QPointF(half, 4))
        path = QPainterPath(QPointF(-half, 0))
        coils = max(3, min(int(length / 16), 40))
        step = length / (coils * 2)
        for index in range(coils * 2):
            path.lineTo(QPointF(-half + step * (index + 0.5), -3 if index % 2 == 0 else 3))
        path.lineTo(QPointF(half, 0))
        p.drawPath(path)
        p.restore()

    def _paint_details(self, p, t, index):
        """Margins and gaps of the selected container, so space is something you can see and drag."""
        if len(self.selection) != 1:
            return
        node_id = self.selection[0]
        owned = index.layout_of_owner.get(node_id) or (node_id if node_id in index.layouts else None)
        if owned and owned in index.layouts:
            self._paint_margins(p, t, index.layouts[owned])
        for gap in self.surface.visible_gaps():
            self._paint_gap(p, t, gap)

    def _paint_margins(self, p, t, geo):
        if not geo.items:
            return
        outer = self.v(geo.rect)
        inner = self.v(geo.content)
        bands = [
            (QRectF(outer.left(), outer.top(), inner.left() - outer.left(), outer.height()), geo.margins[0], "v"),
            (QRectF(outer.left(), outer.top(), outer.width(), inner.top() - outer.top()), geo.margins[1], "h"),
            (QRectF(inner.right(), outer.top(), outer.right() - inner.right(), outer.height()), geo.margins[2], "v"),
            (QRectF(outer.left(), inner.bottom(), outer.width(), outer.bottom() - inner.bottom()), geo.margins[3], "h"),
        ]
        for band, value, orient in bands:
            if band.width() <= 0.5 or band.height() <= 0.5:
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(qcolor(t.gap, 26))
            p.drawRect(band)
        is_root = geo.owner_id == self.surface.doc.root.id
        if is_root:
            # Anchors: the root layout is pinned to all four window edges.
            p.setPen(QPen(qcolor(t.gap, 220), 1.5))
            for start, end in (
                (QPointF(outer.left(), outer.center().y()), QPointF(inner.left(), outer.center().y())),
                (QPointF(inner.right(), outer.center().y()), QPointF(outer.right(), outer.center().y())),
                (QPointF(outer.center().x(), outer.top()), QPointF(outer.center().x(), inner.top())),
                (QPointF(outer.center().x(), inner.bottom()), QPointF(outer.center().x(), outer.bottom())),
            ):
                p.drawLine(start, end)
        font = QFont(QGuiApplication.font())
        font.setPixelSize(10)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        for band, value, _orient in bands:
            if band.width() >= 10 and band.height() >= 10:
                p.setPen(qcolor(t.gap, 240))
                p.drawText(band, Qt.AlignCenter, str(value))

    def _paint_gap(self, p, t, gap):
        rect = self.v(gap["rect"])
        hot = self.gap_hover is not None and self.gap_hover.get("key") == gap["key"]
        p.setPen(Qt.NoPen)
        p.setBrush(qcolor(t.gap, 70 if hot else 34))
        p.drawRect(rect)
        p.setPen(QPen(qcolor(t.gap, 230), 1.5 if hot else 1))
        if gap["vertical"]:
            y = rect.center().y()
            p.drawLine(QPointF(rect.left() + 4, y), QPointF(rect.right() - 4, y))
            handle = QRectF(rect.center().x() - 10, y - 2, 20, 4)
        else:
            x = rect.center().x()
            p.drawLine(QPointF(x, rect.top() + 4), QPointF(x, rect.bottom() - 4))
            handle = QRectF(x - 2, rect.center().y() - 10, 4, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(qcolor(t.gap))
        p.drawRoundedRect(handle, 2, 2)
        if hot or self.surface.gap_drag is not None:
            if gap["vertical"]:
                anchor = QPointF(rect.center().x(), rect.top() - 3)
            else:
                anchor = QPointF(rect.center().x(), rect.top() - 3)
            chip(p, anchor, f"gap {gap['value']}", t.gap, "#FFFFFF", align="center", pixel_size=10)

    # -- hover and selection
    def _paint_hover(self, p, t, index):
        if not self.hover or self.hover in self.selection or self.slot is not None:
            return
        rect = index.rect_of.get(self.hover)
        if rect is None:
            geo = index.layouts.get(self.hover)
            rect = geo.rect if geo else None
        if rect is None:
            return
        view = self.v(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor(t.accent, 200), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(view)
        name = self.surface.display_name(self.hover)
        if name:
            chip(p, QPointF(view.left(), view.top() - 2), name, qcolor(t.accent, 40), t.accent, pixel_size=10, bold=True)

    def _paint_selection(self, p, t, index):
        if self.slot is not None and self.surface.moving:
            return
        for position, node_id in enumerate(self.selection):
            rect = index.rect_of.get(node_id)
            geo = index.layouts.get(node_id)
            if rect is None and geo is not None:
                rect = geo.rect
            if rect is None:
                continue
            view = self.v(rect).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(view)
            if position > 0:
                continue
            node = find_node(self.surface.doc, node_id)
            name = self.surface.display_name(node_id)
            anchor = QPointF(view.left() - 0.5, view.top() - 2)
            if node is self.surface.doc.root:
                anchor = QPointF(view.left() - 0.5, self.v(index.page).top() + 6)
            label_rect = chip(p, anchor, name, t.accent, t.on_accent, pixel_size=11)
            if isinstance(node, Widget) and node is not self.surface.doc.root and len(self.selection) == 1:
                badge = self.surface.size_badge(node)
                if badge:
                    rect = chip(p, QPointF(view.center().x(), view.bottom() + 21), badge, t.surface, t.text, align="center", pixel_size=10, bold=False)
                    p.setPen(QPen(QColor(t.border_strong), 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
                if self.surface.resizable(node_id):
                    for handle in self.surface.handles(view):
                        p.setPen(QPen(QColor(t.accent), 1.25))
                        p.setBrush(QColor("#FFFFFF"))
                        p.drawRect(handle[1])
            del label_rect

    # -- drop indicator
    def _paint_slot(self, p, t):
        slot = self.slot
        if slot is None:
            return
        target = self.v(slot.target).adjusted(0.5, 0.5, -0.5, -0.5) if not slot.target.isNull() else None
        if target is not None:
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(qcolor(t.accent, 16))
            p.drawRoundedRect(target, 4, 4)
        anchor = None
        if slot.cell is not None:
            cell = self.v(slot.cell).adjusted(2, 2, -2, -2)
            pen = QPen(QColor(t.accent), 1.5, Qt.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.setBrush(qcolor(t.accent, 46))
            p.drawRoundedRect(cell, 4, 4)
            paint_glyph(p, "plus", QRectF(cell.center().x() - 7, cell.center().y() - 7, 14, 14), t.accent)
            anchor = QPointF(cell.left(), cell.top() - 3)
        if slot.line is not None:
            a = self.vp(slot.line.p1())
            b = self.vp(slot.line.p2())
            pen = QPen(QColor(t.accent), 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(a, b)
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(a, 3.5, 3.5)
            p.drawEllipse(b, 3.5, 3.5)
            if anchor is None:
                if abs(a.y() - b.y()) < 1:
                    anchor = QPointF(max(a.x(), b.x()) - 6, a.y() - 6)
                    chip(p, anchor, slot.label, t.accent, t.on_accent, align="right", glyph="plus" if self.surface.moving is None else "", pixel_size=11)
                    return
                anchor = QPointF(a.x() + 8, min(a.y(), b.y()) + 22)
        if slot.label and anchor is not None:
            chip(p, anchor, slot.label, t.accent, t.on_accent, glyph="plus" if self.surface.moving is None else "", pixel_size=11)

    # -- tab order
    def _paint_tabs(self, p, t, index):
        centers = []
        hovered_name = None
        if self.hover:
            node = find_node(self.surface.doc, self.hover)
            if isinstance(node, Widget):
                hovered_name = node.object_name
        order = sorted(self.tab_numbers.items(), key=lambda pair: pair[1])
        for name, number in order:
            node_id = index.names.get(name)
            rect = index.rect_of.get(node_id) if node_id else None
            if rect is None:
                continue
            view = self.v(rect)
            centers.append(QPointF(view.right() - 16, view.top() + min(14, view.height() / 2)))
            p.setPen(QPen(qcolor(t.tab, 150), 1))
            p.setBrush(qcolor(t.tab, 8))
            p.drawRoundedRect(view.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        if len(centers) > 1:
            pen = QPen(qcolor(t.tab, 170), 1.5, Qt.DashLine)
            pen.setDashPattern([3, 3])
            p.setPen(pen)
            for a, b in zip(centers, centers[1:]):
                p.drawLine(a, b)
        font = QFont(QGuiApplication.font())
        font.setPixelSize(11)
        font.setWeight(QFont.Bold)
        p.setFont(font)
        for (name, number), center in zip(order, centers):
            done = number < self.tab_next
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(QColor(t.tab) if done or self.tab_next == 1 else qcolor(t.tab, 150))
            p.drawEllipse(center, 11, 11)
            p.setPen(QColor(t.on_tab))
            p.drawText(QRectF(center.x() - 11, center.y() - 11, 22, 22), Qt.AlignCenter, str(number))
        if hovered_name and hovered_name in self.tab_numbers and self.hover in index.rect_of:
            view = self.v(index.rect_of[self.hover])
            chip(p, QPointF(view.right() - 32, view.top() + min(14, view.height() / 2) + 9), f"click to make it {self.tab_next}", t.tab, t.on_tab, align="right", pixel_size=10)

    # -- buddies
    def _paint_buddies(self, p, t, index):
        doc = self.surface.doc
        for node in iter_nodes(doc):
            if not isinstance(node, Widget) or node.class_name != "QLabel":
                continue
            rect = index.rect_of.get(node.id)
            if rect is None:
                continue
            start_rect = self.v(rect)
            start = QPointF(start_rect.right() - 2, start_rect.center().y())
            buddy = get_property(node, "buddy")
            target_id = index.names.get(buddy.body.text) if buddy is not None else None
            if target_id and target_id in index.rect_of:
                end_rect = self.v(index.rect_of[target_id])
                self._link(p, t, start, QPointF(end_rect.left() + 2, end_rect.center().y()), end_rect)
            else:
                p.setPen(QPen(QColor(t.buddy), 1.5))
                p.setBrush(QColor("#FFFFFF"))
                p.drawEllipse(start, 4.5, 4.5)
        if self.buddy_drag is not None:
            source_id, point = self.buddy_drag
            rect = index.rect_of.get(source_id)
            if rect is not None:
                start_rect = self.v(rect)
                target = self.surface.buddy_target_at(point)
                end_rect = self.v(index.rect_of[target]) if target else None
                end = QPointF(end_rect.left() + 2, end_rect.center().y()) if end_rect else QPointF(self.vp(point))
                self._link(p, t, QPointF(start_rect.right() - 2, start_rect.center().y()), end, end_rect)

    def _link(self, p, t, start, end, end_rect):
        if end_rect is not None:
            p.setPen(QPen(qcolor(t.buddy, 200), 1.25))
            p.setBrush(qcolor(t.buddy, 8))
            p.drawRoundedRect(end_rect.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        path = QPainterPath(start)
        dx = max(30.0, abs(end.x() - start.x()) / 2)
        path.cubicTo(QPointF(start.x() + dx, start.y()), QPointF(end.x() - dx, end.y()), end)
        p.setPen(QPen(QColor(t.buddy), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.buddy))
        p.drawEllipse(start, 3.5, 3.5)
        p.drawEllipse(end, 3.5, 3.5)

    # -- menus on a main window
    def _paint_menu(self, p, t, index):
        if index.menubar is None:
            return
        _bar_id, slot_rect, _titles = index.menubar
        rect = self.v(slot_rect).adjusted(2, 3, -2, -3)
        pen = QPen(qcolor(t.accent, 160), 1, Qt.DashLine)
        pen.setDashPattern([3, 2])
        p.setPen(pen)
        p.setBrush(qcolor(t.accent, 14))
        p.drawRoundedRect(rect, 4, 4)
        font = QFont(self.surface.form_font)
        p.setFont(font)
        p.setPen(QColor(t.accent))
        p.drawText(rect, Qt.AlignCenter, "Type here")
        if not self.menu_open:
            return
        panel, rows = self.surface.menu_panel(self.menu_open)
        if panel is None:
            return
        view = self.v(panel)
        paint_shadow(p, view, 6, strength=30, spread=5)
        p.setPen(QPen(QColor(0, 0, 0, 50), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(view, 6, 6)
        for row in rows:
            row_rect = self.v(row["rect"])
            if row["kind"] == "separator":
                p.setPen(QPen(QColor(0, 0, 0, 40), 1))
                p.drawLine(QPointF(row_rect.left() + 8, row_rect.center().y()), QPointF(row_rect.right() - 8, row_rect.center().y()))
                continue
            selected = row.get("id") in self.selection
            if selected:
                p.setPen(Qt.NoPen)
                p.setBrush(qcolor(t.accent, 40))
                p.drawRoundedRect(row_rect.adjusted(3, 1, -3, -1), 4, 4)
            if row["kind"] == "typehere":
                pen = QPen(qcolor(t.accent, 160), 1, Qt.DashLine)
                pen.setDashPattern([3, 2])
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(row_rect.adjusted(4, 2, -4, -2), 4, 4)
                p.setPen(QColor(t.accent))
                p.drawText(row_rect.adjusted(14, 0, 0, 0), Qt.AlignVCenter, row["text"])
            else:
                p.setPen(QColor("#1d1d1f"))
                p.drawText(row_rect.adjusted(14, 0, -10, 0), Qt.AlignVCenter, row["text"])
                if row.get("shortcut"):
                    p.setPen(QColor("#8a8a8e"))
                    p.drawText(row_rect.adjusted(14, 0, -10, 0), Qt.AlignVCenter | Qt.AlignRight, row["shortcut"])

    # -- mode banner
    def _paint_banner(self, p, t):
        texts = {
            "tab": ("order", "Tab order", "Click fields in the order Tab should visit them. Shift-click starts from a field.", t.tab),
            "buddy": ("link", "Buddies", "Drag from a label to the field it names. Its shortcut key will focus that field.", t.buddy),
        }
        if self.mode not in texts:
            return
        glyph, title, body, color = texts[self.mode]
        font = QFont(QGuiApplication.font())
        font.setPixelSize(12)
        bold = QFont(font)
        bold.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(font)
        bold_metrics = QFontMetrics(bold)
        width = 16 + 18 + bold_metrics.horizontalAdvance(title) + 10 + metrics.horizontalAdvance(body) + 16 + 70
        rect = QRectF((self.width() - width) / 2, 14, width, 34)
        paint_shadow(p, rect, 17, strength=22, spread=5)
        p.setPen(QPen(QColor(t.border_strong), 1))
        p.setBrush(QColor(t.surface))
        p.drawRoundedRect(rect, 17, 17)
        x = rect.left() + 14
        paint_glyph(p, glyph, QRectF(x, rect.center().y() - 8, 16, 16), color)
        x += 24
        p.setFont(bold)
        p.setPen(QColor(t.text))
        p.drawText(QRectF(x, rect.top(), 400, rect.height()), Qt.AlignVCenter, title)
        x += bold_metrics.horizontalAdvance(title) + 10
        p.setFont(font)
        p.setPen(QColor(t.muted))
        p.drawText(QRectF(x, rect.top(), 900, rect.height()), Qt.AlignVCenter, body)
        key = QRectF(rect.right() - 62, rect.center().y() - 10, 48, 20)
        p.setPen(QPen(QColor(t.border_strong), 1))
        p.setBrush(QColor(t.surface_alt))
        p.drawRoundedRect(key, 5, 5)
        p.setPen(QColor(t.muted))
        p.drawText(key, Qt.AlignCenter, "Esc")


# --------------------------------------------------------------------------- inline editor
class InlineEditor(QLineEdit):
    """Edits text in place on the canvas. Enter commits, Esc cancels, focus-out commits."""

    def __init__(self, parent):
        super().__init__(parent)
        self.callback = None
        self.hide()
        self.setStyleSheet(
            "QLineEdit { background: #ffffff; color: #111; border: 2px solid %s; border-radius: 4px; padding: 0 4px; }"
            % current().accent
        )

    def open(self, rect: QRectF, text: str, callback, placeholder: str = "") -> None:
        self.callback = callback
        self.setPlaceholderText(placeholder)
        self.setGeometry(rect.toRect().adjusted(-2, -2, 2, 2))
        self.setText(text)
        self.selectAll()
        self.show()
        self.raise_()
        self.setFocus()

    def _finish(self, commit: bool) -> None:
        callback, self.callback = self.callback, None
        self.hide()
        if commit and callback is not None:
            callback(self.text())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._finish(True)
            return
        if event.key() == Qt.Key_Escape:
            self._finish(False)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.callback is not None:
            self._finish(True)


# --------------------------------------------------------------------------- surface
class Surface(QGraphicsView):
    selected = Signal(list)
    hovered = Signal(str)
    context = Signal(QPoint)
    edit_text = Signal(str)

    def __init__(self, name: str = ""):
        super().__init__()
        self.setObjectName("canvasView")
        self.name = name
        scene = QGraphicsScene(self)
        scene.setPalette(runtime_palette())
        scene.setFont(runtime_font())
        self.setScene(scene)
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.host = QWidget()
        self.host.setAttribute(Qt.WA_TranslucentBackground, True)
        self.margin = QVBoxLayout(self.host)
        self.margin.setContentsMargins(64, 56, 64, 72)
        self.page = PageFrame()
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(8, 8 + TITLE_STRIP, 8, 8)
        self.page_layout.setSpacing(0)
        self.margin.addWidget(self.page, 0, Qt.AlignCenter)
        self.proxy = scene.addWidget(self.host)
        self.overlay = Overlay(self)
        self.editor = InlineEditor(self)
        self.realization = Realization()
        self.host.setProperty("realization", self.realization)
        self.index = GeoIndex()
        self.index_dirty = True
        self.doc = None
        self.history = None
        self.form = None
        self.scale_value = 1.0
        self.width_override = 0
        self.fit = False
        self.form_font = runtime_font()
        self.press = None
        self.press_target = None
        self.moving = None
        self.duplicate = False
        self.gap_drag = None
        self.resize_drag = None
        self.page_drag = None
        self.overlay.installEventFilter(self)
        self.overlay.raise_()

    # -- coordinates
    def to_view(self, rect) -> QRectF:
        rect = QRectF(rect)
        a = self.mapFromScene(self.proxy.mapToScene(rect.topLeft()))
        b = self.mapFromScene(self.proxy.mapToScene(rect.bottomRight()))
        return QRectF(QPointF(a), QPointF(b)).normalized()

    def to_view_point(self, point) -> QPointF:
        return QPointF(self.mapFromScene(self.proxy.mapToScene(QPointF(point))))

    def host_pos(self, view_pos) -> QPoint:
        return self.proxy.mapFromScene(self.mapToScene(view_pos)).toPoint()

    def _overlay_host(self, event) -> QPoint:
        return self.host_pos(self.overlay.mapTo(self, event.position().toPoint()))

    # -- document
    def set_tokens(self, tokens):
        self.overlay.tokens = tokens
        self.index_dirty = True
        self.viewport().update()
        QTimer.singleShot(0, self._after_reflow)

    def refresh_overlay(self):
        self.overlay.update()

    def set_document(self, doc, history):
        self.doc = doc
        self.history = history
        self.rebuild()

    def rebuild(self):
        while self.page_layout.count():
            item = self.page_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        # Free the old form now. Nested processEvents() calls never run deferred deletes,
        # so without this a test or a busy session keeps every replaced form alive.
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if self.doc is None:
            return
        self.realization.connect_signals = False
        self.form = self.realization.build(self.doc)
        # Set explicitly: an application palette change (dark chrome) must not reach the form.
        self.form.setPalette(runtime_palette())
        self.form.setFont(self.form_font)
        self.page_layout.addWidget(self.form)
        self.apply_size()
        self.index_dirty = True
        self.refresh_overlay()

    def form_size(self) -> tuple[int, int]:
        if self.doc is None:
            return 640, 480
        width, height = 640, 480
        geometry = get_property(self.doc.root, "geometry")
        if geometry is not None and geometry.body.tag == "rect":
            values = {child.tag: child.text for child in geometry.body.children}
            try:
                width = int(values.get("width", width))
                height = int(values.get("height", height))
            except ValueError:
                pass
        if self.width_override:
            width = self.width_override
        return width, height

    def content_min(self):
        if self.form is None:
            return None
        hint = self.form.minimumSizeHint()
        return hint.width(), hint.height()

    def apply_size(self):
        if self.form is None:
            return
        width, height = self.form_size()
        self.page.title = ""
        title = get_property(self.doc.root, "windowTitle")
        if title is not None:
            self.page.title = title.body.text
        hint = self.form.minimumSizeHint()
        width = max(width, hint.width())
        height = max(height, hint.height())
        self.form.setFixedSize(width, height)
        self.page.setFixedSize(width + 16, height + TITLE_STRIP + 16)
        self.host.adjustSize()
        self.scene().setSceneRect(self.proxy.boundingRect())
        self.page.update()
        self._place_overlay()

    def _place_overlay(self):
        self.overlay.setGeometry(self.viewport().geometry())
        self.overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()

    def drawBackground(self, painter, rect):
        tokens = current()
        painter.fillRect(rect, QColor(tokens.canvas))
        step = 16
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        points = []
        y = top
        while y < rect.bottom():
            x = left
            while x < rect.right():
                points.append(QPointF(x, y))
                x += step
            y += step
        painter.setPen(QPen(QColor(tokens.dots), 1.4 / max(self.scale_value, 0.5)))
        painter.drawPoints(points)

    def set_scale(self, value: float):
        self.scale_value = value
        self.resetTransform()
        self.scale(value, value)
        self.index_dirty = True
        self.refresh_overlay()

    def set_text_size(self, point_size: float):
        self.form_font = runtime_font(point_size)
        if self.form is not None:
            self.form.setFont(self.form_font)
        QTimer.singleShot(0, self._after_reflow)

    def _after_reflow(self):
        self.apply_size()
        self.index_dirty = True
        if self.fit:
            self.fit_width()
        self.refresh_overlay()

    def fit_width(self):
        """Scale so the whole page width fits the view (used for the two-widths view)."""
        page_width = self.page.width() + 96
        available = max(self.viewport().width() - 16, 100)
        self.set_scale(min(1.0, available / page_width))

    def set_preview_width(self, width: int):
        self.width_override = width
        self.apply_size()
        self.index_dirty = True
        self.refresh_overlay()

    # -- index
    def rebuild_index(self):
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        self.margin.activate()
        self.page_layout.activate()
        if self.form is not None and self.form.layout() is not None:
            self.form.layout().activate()
        index = GeoIndex()
        self.index = index
        self.index_dirty = False
        if self.form is None or self.doc is None:
            return
        host = self.host
        index.page = self.page.geometry()
        index.form = QRect(self.form.mapTo(host, QPoint(0, 0)), self.form.size())
        real = self.realization
        for node_id, widget in real.widgets.items():
            if isinstance(widget, QtWidgets.QMenu) or not (widget is real.root or widget.isVisibleTo(host)):
                continue
            rect = QRect(widget.mapTo(host, QPoint(0, 0)), widget.size())
            index.rect_of[node_id] = rect
            index.hits.append((rect, node_id, "widget"))
            index.names[widget.objectName()] = node_id
        for node in iter_nodes(self.doc):
            if isinstance(node, Layout):
                geo = self._layout_geo(node)
                if geo is not None:
                    index.layouts[node.id] = geo
                    if geo.owner_id:
                        index.layout_of_owner[geo.owner_id] = node.id
                    for item in geo.items:
                        if item.kind == "spacer":
                            index.rect_of[item.content_id] = item.rect
                            index.hits.append((item.rect, item.content_id, "spacer"))
            elif isinstance(node, Widget) and node.class_name == "QSplitter" and node.id in index.rect_of:
                geo = self._splitter_geo(node, index)
                if geo is not None:
                    index.layouts[node.id + ":split"] = geo
            elif isinstance(node, Widget) and node.class_name == "QMenuBar" and node.id in index.rect_of:
                index.menubar = self._menubar_geo(node, index)
        index.hits.sort(key=lambda entry: entry[0].width() * entry[0].height())

    def _layout_geo(self, layout: Layout):
        real = self.realization
        qlayout = real.layouts.get(layout.id)
        if qlayout is None:
            return None
        parent = qlayout.parentWidget()
        if parent is None or not (parent is real.root or parent.isVisibleTo(self.host)):
            return None
        geometry = qlayout.geometry()
        if geometry.isNull() or geometry.isEmpty():
            geometry = parent.rect()
        origin = parent.mapTo(self.host, geometry.topLeft())
        rect = QRect(origin, geometry.size())
        content = QRect(parent.mapTo(self.host, qlayout.contentsRect().topLeft()), qlayout.contentsRect().size())
        if rect.height() < MIN_TARGET:
            rect.setHeight(MIN_TARGET)
        if rect.width() < MIN_TARGET:
            rect.setWidth(MIN_TARGET)
        owner = real.holders.get(layout.id)
        owner_id = "" if owner is not None else str(parent.property("formId") or "")
        margins = qlayout.contentsMargins()
        geo = LayoutGeo(
            id=layout.id,
            cls=layout.class_name,
            rect=rect,
            content=content if not content.isEmpty() else rect,
            owner_id=owner_id,
            margins=(margins.left(), margins.top(), margins.right(), margins.bottom()),
            vertical=layout.class_name != "QHBoxLayout",
        )
        spacing = qlayout.spacing()
        geo.spacing = spacing if spacing >= 0 else 6
        if hasattr(qlayout, "horizontalSpacing"):
            geo.hspacing = max(qlayout.horizontalSpacing(), 0)
            geo.vspacing = max(qlayout.verticalSpacing(), 0)
        order = real.order.get(layout.id, [])
        for item in layout_items(layout):
            content_node = item_content(item)
            if content_node is None:
                continue
            kind = "widget"
            item_rect = None
            if isinstance(content_node, Widget):
                widget = real.widgets.get(content_node.id)
                if widget is not None:
                    item_rect = QRect(widget.mapTo(self.host, QPoint(0, 0)), widget.size())
            elif isinstance(content_node, Layout):
                kind = "layout"
                holder = real.holders.get(content_node.id)
                if holder is not None:
                    item_rect = QRect(holder.mapTo(self.host, QPoint(0, 0)), holder.size())
            elif isinstance(content_node, Spacer):
                kind = "spacer"
                if content_node.id in order:
                    q_item = qlayout.itemAt(order.index(content_node.id))
                    if q_item is not None:
                        g = q_item.geometry()
                        item_rect = QRect(parent.mapTo(self.host, g.topLeft()), g.size())
            if item_rect is None:
                continue
            geo.items.append(
                ItemGeo(
                    content_id=content_node.id,
                    item_id=item.id,
                    rect=item_rect,
                    kind=kind,
                    row=int(item.attrib.get("row", "0") or 0),
                    col=int(item.attrib.get("column", "0") or 0),
                    rowspan=int(item.attrib.get("rowspan", "1") or 1),
                    colspan=int(item.attrib.get("colspan", "1") or 1),
                )
            )
        if layout.class_name in ("QGridLayout", "QFormLayout"):
            for item in geo.items:
                span = item.colspan if layout.class_name == "QGridLayout" else (2 if item.col == 2 or item.colspan > 1 else 1)
                start_col = 0 if layout.class_name == "QFormLayout" and span == 2 else item.col
                for r in range(item.row, item.row + (item.rowspan if layout.class_name == "QGridLayout" else 1)):
                    for c in range(start_col, start_col + span):
                        geo.cells[(r, c)] = item
        if layout.class_name == "QFormLayout":
            self._form_rows(layout, geo, qlayout, parent)
        elif layout.class_name == "QGridLayout":
            self._grid_rows(geo, qlayout, parent)
        return geo

    def _form_rows(self, layout, geo, qlayout, parent):
        dense = form_rows(layout)
        rows = {}
        for item in geo.items:
            rows.setdefault(item.row, []).append(item)
        label_right = geo.content.left()
        field_left = geo.content.left() + geo.content.width() // 3
        for item in geo.items:
            if item.col == 0 and item.colspan < 2:
                label_right = max(label_right, item.rect.right())
            elif item.col == 1:
                field_left = item.rect.left() if field_left == geo.content.left() + geo.content.width() // 3 else min(field_left, item.rect.left())
        if not any(item.col == 1 for item in geo.items) and any(item.col == 0 for item in geo.items):
            field_left = label_right + max(geo.hspacing, 6)
        geo.label_right = label_right
        geo.field_left = field_left
        for model_row in sorted(rows, key=lambda row: dense.get(row, row)):
            items = rows[model_row]
            top = min(item.rect.top() for item in items)
            bottom = max(item.rect.bottom() for item in items)
            geo.rows.append((model_row, top, bottom))

    def _grid_rows(self, geo, qlayout, parent):
        """Row and column extents. Cell rectangles where Qt has them, item bounds otherwise."""
        geo.rows = []
        geo.cols = []
        for r in range(qlayout.rowCount()):
            cell = _cell(qlayout, r, None)
            if cell is not None:
                top = parent.mapTo(self.host, cell.topLeft()).y()
                geo.rows.append((r, top, top + cell.height() - 1))
        for c in range(qlayout.columnCount()):
            cell = _cell(qlayout, None, c)
            if cell is not None:
                left = parent.mapTo(self.host, cell.topLeft()).x()
                geo.cols.append((c, left, left + cell.width() - 1))

    def _splitter_geo(self, node, index):
        rect = index.rect_of[node.id]
        widget = self.realization.widgets.get(node.id)
        geo = LayoutGeo(id=node.id + ":split", cls="QSplitter", rect=rect, content=rect, owner_id=node.id)
        geo.vertical = widget is not None and widget.orientation() == Qt.Vertical
        for position, child in enumerate(child_widgets(node)):
            child_rect = index.rect_of.get(child.id)
            if child_rect is not None:
                geo.items.append(ItemGeo(child.id, "", child_rect, "pane", row=position))
        return geo

    def _menubar_geo(self, node, index):
        bar = self.realization.widgets.get(node.id)
        if bar is None:
            return None
        origin = bar.mapTo(self.host, QPoint(0, 0))
        titles = []
        right = 4
        for action in bar.actions():
            g = bar.actionGeometry(action)
            if g.isNull():
                continue
            rect = QRect(origin + g.topLeft(), g.size())
            menu = action.menu()
            menu_id = str(menu.property("formId")) if menu is not None and menu.property("formId") else ""
            titles.append((rect, menu_id, action.text()))
            right = max(right, g.right() + 1)
        height = max(bar.height(), 22)
        slot = QRect(origin.x() + right + 4, origin.y(), 84, height)
        return (node.id, slot, titles)

    # -- descriptions the overlay shows
    def display_name(self, node_id: str) -> str:
        node = find_node(self.doc, node_id)
        if isinstance(node, Widget):
            return node.object_name or node.class_name
        if isinstance(node, Layout):
            return node.object_name or LAYOUT_WORDS.get(node.class_name, node.class_name)
        if isinstance(node, Spacer):
            return node.name or "spacer"
        if isinstance(node, Action):
            return node.name
        return ""

    def size_badge(self, node: Widget) -> str:
        rect = self.index.rect_of.get(node.id)
        if rect is None:
            return ""
        default = class_default(self.doc, node.class_name)
        h_mode = sizing.axis_mode(node, "h", default)[0]
        v_mode = sizing.axis_mode(node, "v", default)[0]
        return f"{sizing.badge(h_mode, v_mode)}  ·  {rect.width()} × {rect.height()}"

    def parent_layout_id(self, node_id: str) -> str:
        if self.doc is None:
            return ""
        item = resolve_layout_item(self.doc, node_id)
        if item is None:
            return ""
        located = locate(self.doc, item.id)
        if located is not None and isinstance(located[0], Layout):
            return located[0].id
        return ""

    def resizable(self, node_id: str) -> bool:
        return bool(self.parent_layout_id(node_id))

    def handles(self, view: QRectF):
        size = 7
        half = size / 2
        return [
            ("h", QRectF(view.right() - half, view.center().y() - half, size, size)),
            ("v", QRectF(view.center().x() - half, view.bottom() - half, size, size)),
            ("hv", QRectF(view.right() - half, view.bottom() - half, size, size)),
        ]

    def gaps(self, geo: LayoutGeo):
        """Gap rectangles between neighbours, in host coordinates."""
        found = []
        if geo.cls in ("QVBoxLayout", "QHBoxLayout") and len(geo.items) > 1:
            items = sorted(geo.items, key=lambda item: item.rect.top() if geo.vertical else item.rect.left())
            thick = max(geo.spacing, 2)
            for index, (a, b) in enumerate(zip(items, items[1:])):
                if geo.vertical:
                    middle = (a.rect.bottom() + 1 + b.rect.top()) // 2
                    rect = QRect(geo.content.left(), middle - thick // 2, geo.content.width(), thick)
                else:
                    middle = (a.rect.right() + 1 + b.rect.left()) // 2
                    rect = QRect(middle - thick // 2, geo.content.top(), thick, geo.content.height())
                found.append({"key": (geo.id, index), "rect": rect, "vertical": geo.vertical, "value": geo.spacing, "prop": "spacing", "layout_id": geo.id})
        elif geo.cls in ("QFormLayout", "QGridLayout") and len(geo.rows) > 1:
            prop = "verticalSpacing"
            thick = max(geo.vspacing, 2)
            for index, (a, b) in enumerate(zip(geo.rows, geo.rows[1:])):
                middle = (a[2] + 1 + b[1]) // 2
                rect = QRect(geo.content.left(), middle - thick // 2, geo.content.width(), thick)
                found.append({"key": (geo.id, "r", index), "rect": rect, "vertical": True, "value": geo.vspacing, "prop": prop, "layout_id": geo.id})
            if geo.cls == "QGridLayout":
                cols = getattr(geo, "cols", [])
                thick_h = max(geo.hspacing, 2)
                for index, (a, b) in enumerate(zip(cols, cols[1:])):
                    middle = (a[2] + 1 + b[1]) // 2
                    rect = QRect(middle - thick_h // 2, geo.content.top(), thick_h, geo.content.height())
                    found.append({"key": (geo.id, "c", index), "rect": rect, "vertical": False, "value": geo.hspacing, "prop": "horizontalSpacing", "layout_id": geo.id})
        return found

    def menu_panel(self, menu_id: str):
        index = self.index
        if index.menubar is None:
            return None, []
        title_rect = None
        for rect, owner, _text in index.menubar[2]:
            if owner == menu_id:
                title_rect = rect
        menu_node = find_node(self.doc, menu_id)
        menu_widget = self.realization.widgets.get(menu_id)
        if title_rect is None or menu_node is None or menu_widget is None:
            return None, []
        rows = []
        metrics = QFontMetrics(QFont(QGuiApplication.font()))
        width = 180
        entries = []
        actions = {action.objectName(): action for action in menu_widget.actions()}
        root_actions = {part.name: part for part in self.doc.root.body if isinstance(part, Action)}
        for position, part in enumerate(menu_node.body):
            if not isinstance(part, ActionRef):
                continue
            if part.name == "separator":
                entries.append({"kind": "separator", "text": "", "position": position})
                continue
            action = actions.get(part.name)
            text = action.text() if action is not None else part.name
            shortcut = action.shortcut().toString() if action is not None else ""
            node = root_actions.get(part.name)
            entries.append({"kind": "action", "text": text.replace("&", ""), "shortcut": shortcut, "id": node.id if node else "", "position": position})
            width = max(width, metrics.horizontalAdvance(text) + metrics.horizontalAdvance(shortcut) + 70)
        entries.append({"kind": "typehere", "text": "Type here", "position": -1})
        top = title_rect.bottom() + 2
        y = top + 4
        for entry in entries:
            height = 9 if entry["kind"] == "separator" else 26
            entry["rect"] = QRect(title_rect.left(), y, width, height)
            rows.append(entry)
            y += height
        panel = QRect(title_rect.left(), top, width, y - top + 4)
        return panel, rows

    # -- hit testing
    def hit(self, pos: QPoint):
        for rect, node_id, kind in self.index.hits:
            if rect.contains(pos):
                return node_id
        return None

    def buddy_target_at(self, pos: QPoint):
        node_id = self.hit(pos)
        node = find_node(self.doc, node_id) if node_id else None
        if isinstance(node, Widget) and node.class_name in INPUT_CLASSES:
            return node_id
        return None

    def visible_gaps(self):
        """Gaps worth showing: all of a selected container's, or the ones touching a selected leaf."""
        if len(self.overlay.selection) != 1 or self.overlay.mode != "design":
            return []
        node_id = self.overlay.selection[0]
        owned = self.index.layout_of_owner.get(node_id) or (node_id if node_id in self.index.layouts else None)
        if owned and owned in self.index.layouts:
            return self.gaps(self.index.layouts[owned])
        parent = self.parent_layout_id(node_id)
        geo = self.index.layouts.get(parent) if parent else None
        rect = self.index.rect_of.get(node_id)
        if geo is None or rect is None:
            return []
        reach = max(geo.spacing, geo.vspacing, geo.hspacing) + 4
        near = rect.adjusted(-reach, -reach, reach, reach)
        return [gap for gap in self.gaps(geo) if gap["rect"].intersects(near)]

    def _gap_at(self, pos: QPoint):
        for gap in self.visible_gaps():
            rect = gap["rect"]
            grow = QRect(rect)
            if gap["vertical"] and rect.height() < 8:
                grow.adjust(0, -(8 - rect.height()) // 2 - 1, 0, (8 - rect.height()) // 2 + 1)
            if not gap["vertical"] and rect.width() < 8:
                grow.adjust(-(8 - rect.width()) // 2 - 1, 0, (8 - rect.width()) // 2 + 1, 0)
            if grow.contains(pos):
                return gap
        return None

    def _handle_at(self, view_pos: QPoint):
        if len(self.overlay.selection) != 1:
            return None
        node_id = self.overlay.selection[0]
        rect = self.index.rect_of.get(node_id)
        if rect is None or not self.resizable(node_id):
            return None
        view = self.to_view(rect)
        for axis, handle in self.handles(view):
            if handle.adjusted(-4, -4, 4, 4).contains(QPointF(view_pos)):
                return axis
        return None

    def _page_edge_at(self, pos: QPoint):
        page = self.index.page.adjusted(8, 8, -8, -8)
        if page.isNull():
            return None
        near_right = abs(pos.x() - page.right()) <= 6 and page.top() <= pos.y() <= page.bottom()
        near_bottom = abs(pos.y() - page.bottom()) <= 6 and page.left() <= pos.x() <= page.right()
        if near_right and near_bottom:
            return "hv"
        if near_right:
            return "h"
        if near_bottom:
            return "v"
        return None

    def _menu_hit(self, pos: QPoint):
        index = self.index
        if index.menubar is None or self.overlay.mode != "design":
            return None
        bar_id, slot, titles = index.menubar
        if self.overlay.menu_open:
            _panel, rows = self.menu_panel(self.overlay.menu_open)
            for row in rows:
                if row["rect"].contains(pos):
                    return ("row", row)
        if slot.contains(pos):
            return ("newmenu", bar_id)
        for rect, menu_id, _text in titles:
            if rect.contains(pos) and menu_id:
                return ("title", menu_id)
        return None

    # -- drop slots
    def slot_at(self, pos: QPoint, content_class: str = "", moving: str = "") -> Slot | None:
        index = self.index
        doc = self.doc
        candidates = [geo for geo in index.layouts.values() if geo.rect.contains(pos)]
        if moving:
            candidates = [geo for geo in candidates if not self._inside(geo, moving)]
        candidates.sort(key=lambda geo: geo.rect.width() * geo.rect.height())
        hit_id = self.hit(pos)
        bare = None
        if hit_id and hit_id != moving:
            node = find_node(doc, hit_id)
            if (
                isinstance(node, Widget)
                and is_container(node)
                and widget_layout(node) is None
                and node.class_name not in PAGE_CLASSES
                and node.class_name not in ("QMainWindow", "QMenuBar", "QToolBar", "QStatusBar")
                and not (moving and self._is_ancestor(moving, hit_id))
            ):
                bare = node
        if bare is not None:
            rect = index.rect_of[bare.id]
            if not candidates or rect.width() * rect.height() <= candidates[0].rect.width() * candidates[0].rect.height():
                return Slot(
                    mode="newlayout",
                    widget_id=bare.id,
                    target=rect,
                    line=QLineF(rect.left() + 10, rect.center().y(), rect.right() - 10, rect.center().y()),
                    label=f"Into {bare.object_name} · makes a vertical layout",
                )
        if not candidates:
            return None
        geo = candidates[0]
        if geo.cls in ("QVBoxLayout", "QHBoxLayout"):
            return self._box_slot(geo, pos, moving)
        if geo.cls == "QGridLayout":
            return self._grid_slot(geo, pos, moving)
        if geo.cls == "QFormLayout":
            return self._form_slot(geo, pos, content_class, moving)
        if geo.cls == "QSplitter" and not moving:
            return self._split_slot(geo, pos)
        return None

    def _inside(self, geo: LayoutGeo, moving: str) -> bool:
        owner = geo.owner_id
        if not owner:
            return False
        return owner == moving or self._is_ancestor(moving, owner)

    def _is_ancestor(self, ancestor_id: str, node_id: str) -> bool:
        ancestor = self.realization.widgets.get(ancestor_id)
        widget = self.realization.widgets.get(node_id)
        return ancestor is not None and widget is not None and ancestor.isAncestorOf(widget)

    def _layout_name(self, geo) -> str:
        node = find_node(self.doc, geo.id.split(":")[0])
        if isinstance(node, Layout):
            return node.object_name or LAYOUT_NAMES.get(geo.cls, "layout")
        if isinstance(node, Widget):
            return node.object_name
        return "layout"

    def _box_slot(self, geo, pos, moving):
        vertical = geo.vertical
        items = sorted(geo.items, key=lambda item: item.rect.top() if vertical else item.rect.left())
        model_layout = find_node(self.doc, geo.id)
        order = [item.id for item in layout_items(model_layout)]
        content = geo.content
        name = self._layout_name(geo)
        if not items:
            line = QLineF(content.left() + 8, content.center().y(), content.right() - 8, content.center().y())
            return Slot("insert", geo.id, 0, target=geo.rect, line=line, label=f"Into {name}")
        position = len(items)
        for number, item in enumerate(items):
            middle = item.rect.center().y() if vertical else item.rect.center().x()
            if (pos.y() if vertical else pos.x()) < middle:
                position = number
                break
        if position == 0:
            edge = items[0].rect.top() - geo.spacing / 2 if vertical else items[0].rect.left() - geo.spacing / 2
        elif position == len(items):
            edge = items[-1].rect.bottom() + geo.spacing / 2 + 1 if vertical else items[-1].rect.right() + geo.spacing / 2 + 1
        else:
            before, after = items[position - 1], items[position]
            edge = (before.rect.bottom() + after.rect.top() + 1) / 2 if vertical else (before.rect.right() + after.rect.left() + 1) / 2
        if vertical:
            line = QLineF(content.left() + 2, edge, content.right() - 2, edge)
        else:
            line = QLineF(edge, content.top() + 2, edge, content.bottom() - 2)
        model_index = order.index(items[position].item_id) if position < len(items) else len(order)
        if moving:
            moving_item = resolve_layout_item(self.doc, moving)
            if moving_item is not None and moving_item.id in order:
                current_index = order.index(moving_item.id)
                if model_index in (current_index, current_index + 1):
                    return Slot("noop", geo.id, model_index, target=geo.rect, line=line, label="Same place")
        return Slot("insert", geo.id, model_index, target=geo.rect, line=line, label=f"Into {name} · position {position + 1}")

    def _grid_slot(self, geo, pos, moving):
        name = self._layout_name(geo)
        rows = geo.rows
        cols = getattr(geo, "cols", [])
        moving_cells = set()
        if moving:
            for key, item in geo.cells.items():
                if item.content_id == moving:
                    moving_cells.add(key)
        taken = {key for key in geo.cells if key not in moving_cells}
        if not rows or not cols:
            return Slot("cell", geo.id, attrib={"row": "0", "column": "0"}, target=geo.rect, cell=geo.content, label=f"Into {name} · row 1, column 1")
        candidates = []
        default_h = max(28, min(row[2] - row[1] for row in rows) + 1)
        default_w = max(60, min(col[2] - col[1] for col in cols) + 1)
        all_rows = list(rows) + [(len(rows), rows[-1][2] + geo.vspacing + 1, rows[-1][2] + geo.vspacing + default_h)]
        all_cols = list(cols) + [(len(cols), cols[-1][2] + geo.hspacing + 1, cols[-1][2] + geo.hspacing + default_w)]
        for r, top, bottom in all_rows:
            for c, left, right in all_cols:
                if (r, c) in taken:
                    continue
                if r == len(rows) and c == len(cols):
                    continue
                rect = QRect(left, top, right - left + 1, bottom - top + 1)
                distance = 0 if rect.contains(pos) else (rect.center() - pos).manhattanLength()
                candidates.append((distance, r, c, rect))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        _distance, r, c, rect = candidates[0]
        extra = " · new row" if r == len(rows) else (" · new column" if c == len(cols) else "")
        target = geo.rect.united(rect)
        return Slot("cell", geo.id, attrib={"row": str(r), "column": str(c)}, target=target, cell=rect, label=f"Row {r + 1}, column {c + 1}{extra}")

    def _form_slot(self, geo, pos, content_class, moving):
        name = self._layout_name(geo)
        content = geo.content
        label_side = content_class == "QLabel"
        if not geo.rows:
            attrib = {"row": "0", "column": "0" if label_side else "1"}
            line = QLineF(content.left() + 8, content.center().y(), content.right() - 8, content.center().y())
            return Slot("cell", geo.id, attrib=attrib, target=geo.rect, line=line, label=f"Into {name} · row 1")
        moving_id = moving
        for number, (model_row, top, bottom) in enumerate(geo.rows):
            next_top = geo.rows[number + 1][1] if number + 1 < len(geo.rows) else bottom + geo.vspacing + 1
            prev_bottom = geo.rows[number - 1][2] if number > 0 else top - geo.vspacing - 1
            zone_top = (prev_bottom + top) / 2
            zone_bottom = (bottom + next_top) / 2
            if not (zone_top <= pos.y() <= zone_bottom):
                continue
            left_half = pos.x() < geo.field_left - max(geo.hspacing, 6) / 2
            column = 0 if left_half else 1
            occupant = geo.cells.get((model_row, column))
            if occupant is not None and occupant.content_id == moving_id:
                occupant = None
            spanning = geo.cells.get((model_row, 0)) is not None and geo.cells.get((model_row, 0)).colspan > 1
            if occupant is None and not spanning:
                if column == 0:
                    cell = QRect(content.left(), top, geo.label_right - content.left() + 1, bottom - top + 1)
                else:
                    cell = QRect(geo.field_left, top, content.right() - geo.field_left + 1, bottom - top + 1)
                side = "label" if column == 0 else "field"
                return Slot("cell", geo.id, attrib={"row": str(model_row), "column": str(column)}, target=geo.rect, cell=cell, label=f"Row {number + 1} · {side}")
            middle = (top + bottom) / 2
            before = pos.y() < middle
            new_row = model_row if before else model_row + 1
            edge = (prev_bottom + top) / 2 if before else (bottom + next_top) / 2
            line = QLineF(content.left() + 2, edge, content.right() - 2, edge)
            attrib = {"row": str(new_row), "column": "0" if label_side else "1"}
            return Slot("row", geo.id, attrib=attrib, target=geo.rect, line=line, label=f"New row {number + (1 if before else 2)}", new_row=new_row)
        last = geo.rows[-1]
        if pos.y() > last[2]:
            new_row = last[0] + 1
            edge = last[2] + geo.vspacing / 2 + 1
            line = QLineF(content.left() + 2, edge, content.right() - 2, edge)
            attrib = {"row": str(new_row), "column": "0" if label_side else "1"}
            return Slot("row", geo.id, attrib=attrib, target=geo.rect, line=line, label=f"New row {len(geo.rows) + 1}", new_row=new_row)
        first = geo.rows[0]
        edge = first[1] - geo.vspacing / 2
        line = QLineF(content.left() + 2, edge, content.right() - 2, edge)
        attrib = {"row": str(first[0]), "column": "0" if label_side else "1"}
        return Slot("row", geo.id, attrib=attrib, target=geo.rect, line=line, label="New row 1", new_row=first[0])

    def _split_slot(self, geo, pos):
        items = sorted(geo.items, key=lambda item: item.rect.top() if geo.vertical else item.rect.left())
        position = len(items)
        for number, item in enumerate(items):
            middle = item.rect.center().y() if geo.vertical else item.rect.center().x()
            if (pos.y() if geo.vertical else pos.x()) < middle:
                position = number
                break
        rect = geo.rect
        if items:
            reference = items[position].rect if position < len(items) else items[-1].rect
            edge = (reference.top() if geo.vertical else reference.left()) if position < len(items) else (reference.bottom() if geo.vertical else reference.right())
        else:
            edge = rect.center().y() if geo.vertical else rect.center().x()
        line = QLineF(rect.left() + 4, edge, rect.right() - 4, edge) if geo.vertical else QLineF(edge, rect.top() + 4, edge, rect.bottom() - 4)
        return Slot("pane", geo.owner_id, position, target=rect, line=line, label=f"Splitter pane {position + 1}")

    # -- commits
    def commands_for_drop(self, content, slot: Slot):
        doc = self.doc
        if slot.mode == "newlayout":
            layout_id = doc.alloc()
            command = Compound(
                [
                    EnsureLayout(slot.widget_id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                    InsertItem(layout_id, 0, make_item(doc, content)),
                ]
            )
        elif slot.mode == "pane":
            if not isinstance(content, Widget):
                return None
            command = InsertChild(slot.layout_id, slot.index, content)
        elif slot.mode == "row":
            from spikes.form_builder.commands import insert_form_row

            layout = find_node(doc, slot.layout_id)
            command = insert_form_row(doc, layout, slot.new_row, make_item(doc, content, **slot.attrib))
        elif slot.mode in ("insert", "cell"):
            command = InsertItem(slot.layout_id, slot.index if slot.mode == "insert" else 10**6, make_item(doc, content, **slot.attrib))
        else:
            return None
        return with_tab_splice(doc, command, content)

    def commands_for_move(self, node_id: str, slot: Slot):
        doc = self.doc
        item = resolve_layout_item(doc, node_id)
        if item is None or slot.mode == "noop":
            return None
        if slot.mode == "newlayout":
            layout_id = doc.alloc()
            return Compound(
                [
                    EnsureLayout(slot.widget_id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                    MoveItem(item.id, layout_id, 0, {}),
                ]
            )
        if slot.mode == "insert":
            return MoveItem(item.id, slot.layout_id, slot.index, {})
        if slot.mode == "cell":
            attrib = dict(slot.attrib)
            return MoveItem(item.id, slot.layout_id, 10**6, attrib)
        if slot.mode == "row":
            layout = find_node(doc, slot.layout_id)
            steps = []
            for existing in layout_items(layout):
                if existing.id == item.id:
                    continue
                row = int(existing.attrib.get("row", "0") or 0)
                if row >= slot.new_row:
                    attrib = dict(existing.attrib)
                    attrib["row"] = str(row + 1)
                    steps.append(SetItemAttrib(existing.id, attrib))
            steps.append(MoveItem(item.id, slot.layout_id, 10**6, dict(slot.attrib)))
            return Compound(steps)
        return None

    # -- events
    def eventFilter(self, watched, event):
        if watched is not self.overlay or self.doc is None:
            return False
        kind = event.type()
        if kind == QEvent.MouseButtonPress:
            return self._press(event)
        if kind == QEvent.MouseMove:
            return self._move(event)
        if kind == QEvent.MouseButtonRelease:
            return self._release(event)
        if kind == QEvent.MouseButtonDblClick:
            return self._double(event)
        if kind == QEvent.Wheel:
            if event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
                step = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
                window = self.window()
                if hasattr(window, "set_zoom_value"):
                    window.set_zoom_value(self.scale_value * step)
                return True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().x() // 2)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - event.angleDelta().y() // 2)
            return True
        if kind == QEvent.Leave:
            self.overlay.hover = None
            self.overlay.gap_hover = None
            self.refresh_overlay()
        return False

    def _press(self, event):
        if self.index_dirty:
            self.rebuild_index()
        self.setFocus()
        pos = self._overlay_host(event)
        view_pos = self.overlay.mapTo(self, event.position().toPoint())
        self.press = pos
        self.moving = None
        if event.button() == Qt.RightButton:
            node_id = self.hit(pos)
            if node_id and node_id not in self.overlay.selection:
                self.selected.emit([node_id])
            self.context.emit(event.globalPosition().toPoint())
            self.press = None
            return True
        if event.button() != Qt.LeftButton:
            return True
        mode = self.overlay.mode
        if mode == "design":
            menu = self._menu_hit(pos)
            if menu is not None:
                self.press_target = ("menu", menu)
                return True
            if self.overlay.menu_open:
                self.overlay.menu_open = ""
            axis = self._handle_at(view_pos)
            if axis:
                node_id = self.overlay.selection[0]
                widget = self.realization.widgets.get(node_id)
                self.resize_drag = {"axis": axis, "id": node_id, "start": pos, "size": widget.size() if widget else QSize()}
                return True
            gap = self._gap_at(pos)
            if gap is not None:
                qlayout = self.realization.layouts.get(gap["layout_id"])
                self.gap_drag = dict(gap, start=pos, qlayout=qlayout, live=gap["value"])
                return True
            edge = self._page_edge_at(pos)
            if edge:
                self.page_drag = {"axis": edge, "start": view_pos, "size": self.form_size()}
                return True
        if mode == "buddy":
            node_id = self.hit(pos)
            node = find_node(self.doc, node_id) if node_id else None
            if isinstance(node, Widget) and node.class_name == "QLabel":
                self.overlay.buddy_drag = (node_id, pos)
                self.selected.emit([node_id])
                return True
        self.press_target = ("hit", self.hit(pos))
        self.duplicate = bool(event.modifiers() & Qt.AltModifier)
        return True

    def _move(self, event):
        pos = self._overlay_host(event)
        view_pos = self.overlay.mapTo(self, event.position().toPoint())
        if self.index_dirty:
            self.rebuild_index()
        buttons = event.buttons()
        if self.resize_drag is not None:
            self._live_resize(pos, event.modifiers())
            return True
        if self.gap_drag is not None:
            self._live_gap(pos, event.modifiers())
            return True
        if self.page_drag is not None:
            self._live_page(view_pos, event.modifiers())
            return True
        if self.overlay.buddy_drag is not None:
            self.overlay.buddy_drag = (self.overlay.buddy_drag[0], pos)
            self.refresh_overlay()
            return True
        if buttons & Qt.LeftButton and self.press is not None and self.overlay.mode == "design":
            target = self.press_target[1] if self.press_target and self.press_target[0] == "hit" else None
            if self.moving is None and target and (pos - self.press).manhattanLength() > 5:
                if resolve_layout_item(self.doc, target) is not None and target != self.doc.root.id:
                    self.moving = target
                    if target not in self.overlay.selection:
                        self.selected.emit([target])
            if self.moving:
                node = find_node(self.doc, self.moving)
                class_name = node.class_name if isinstance(node, Widget) else ""
                slot = self.slot_at(pos, class_name, moving="" if self.duplicate else self.moving)
                if slot is not None and self.duplicate:
                    slot.label = "Copy · " + slot.label
                self.overlay.slot = slot
                self.hovered.emit(slot.label if slot else "No layout here. Drop inside the window.")
                self.setCursor(Qt.ClosedHandCursor if slot is not None else Qt.ForbiddenCursor)
                self.refresh_overlay()
            return True
        # Hover only.
        hover = self.hit(pos)
        gap = self._gap_at(pos) if self.overlay.mode == "design" else None
        cursor = Qt.ArrowCursor
        if self.overlay.mode == "design":
            axis = self._handle_at(view_pos)
            edge = self._page_edge_at(pos)
            if axis:
                cursor = {"h": Qt.SizeHorCursor, "v": Qt.SizeVerCursor, "hv": Qt.SizeFDiagCursor}[axis]
            elif gap is not None:
                cursor = Qt.SplitVCursor if gap["vertical"] else Qt.SplitHCursor
            elif edge:
                cursor = {"h": Qt.SizeHorCursor, "v": Qt.SizeVerCursor, "hv": Qt.SizeFDiagCursor}[edge]
            elif self._menu_hit(pos) is not None:
                cursor = Qt.PointingHandCursor
            elif hover:
                cursor = Qt.OpenHandCursor if hover in self.overlay.selection and resolve_layout_item(self.doc, hover) else Qt.ArrowCursor
        elif self.overlay.mode in ("tab", "buddy") and hover:
            cursor = Qt.PointingHandCursor
        self.overlay.setCursor(cursor)
        changed = hover != self.overlay.hover or (gap or {}).get("key") != (self.overlay.gap_hover or {}).get("key")
        self.overlay.hover = hover
        self.overlay.gap_hover = gap
        if changed:
            self.hovered.emit(self._hover_text(hover, gap))
            self.refresh_overlay()
        return True

    def _hover_text(self, hover, gap) -> str:
        if gap is not None:
            return f"Gap {gap['value']} px. Drag to change it: Alt for 1 px steps, Shift for 8."
        if not hover:
            return ""
        node = find_node(self.doc, hover)
        mode = self.overlay.mode
        if mode == "tab":
            return "Click to make this the next stop in the tab order."
        if mode == "buddy":
            return "Drag from a label to the field it describes."
        if isinstance(node, Widget):
            return f"{node.object_name} · {node.class_name}. Drag to move, Alt-drag to copy, double-click to edit text."
        if isinstance(node, Spacer):
            return f"{node.name} · spacer. It soaks up spare room."
        return ""

    def _release(self, event):
        pos = self._overlay_host(event)
        try:
            if self.resize_drag is not None:
                self._commit_resize(pos, event.modifiers())
                return True
            if self.gap_drag is not None:
                self._commit_gap()
                return True
            if self.page_drag is not None:
                self._commit_page(pos, event.modifiers())
                return True
            if self.overlay.buddy_drag is not None:
                source, _point = self.overlay.buddy_drag
                self.overlay.buddy_drag = None
                target = self.buddy_target_at(pos)
                if target and self.history is not None:
                    target_node = find_node(self.doc, target)
                    self.history.execute(SetProperty(source, "buddy", prop_cstring("buddy", target_node.object_name)))
                self.refresh_overlay()
                return True
            if self.press_target and self.press_target[0] == "menu":
                self._menu_click(self.press_target[1])
                return True
            if self.moving:
                slot = self.overlay.slot
                if slot is not None and self.history is not None:
                    if self.duplicate:
                        node = find_node(self.doc, self.moving)
                        if isinstance(node, Widget):
                            clone = clone_widget(self.doc, node)
                            command = self.commands_for_drop(clone, slot)
                            if command is not None:
                                self.history.execute(command)
                                self.selected.emit([clone.id])
                    else:
                        command = self.commands_for_move(self.moving, slot)
                        if command is not None:
                            moved = self.moving
                            self.history.execute(command)
                            self.selected.emit([moved])
                return True
            if self.press is None:
                return True
            mode = self.overlay.mode
            if mode == "tab":
                self._tab_click(pos, event.modifiers())
            elif mode == "design":
                self._select_at(pos, event.modifiers())
            return True
        finally:
            self.press = None
            self.press_target = None
            self.moving = None
            self.duplicate = False
            self.resize_drag = None
            self.gap_drag = None
            self.page_drag = None
            self.overlay.slot = None
            self.setCursor(Qt.ArrowCursor)
            self.refresh_overlay()

    def _double(self, event):
        pos = self._overlay_host(event)
        if self.overlay.mode != "design":
            return True
        view_pos = self.overlay.mapTo(self, event.position().toPoint())
        axis = self._handle_at(view_pos)
        if axis and self.history is not None:
            node = find_node(self.doc, self.overlay.selection[0])
            steps = []
            for part in ("h", "v") if axis == "hv" else (axis,):
                command = sizing.set_axis(node, part, "hug", class_default(self.doc, node.class_name))
                if command is not None:
                    steps.append(command)
            if steps:
                self.history.execute(steps[0] if len(steps) == 1 else Compound(steps))
            return True
        node_id = self.hit(pos)
        if node_id:
            self.selected.emit([node_id])
            self.edit_text.emit(node_id)
        return True

    def _select_at(self, pos, modifiers):
        node_id = self.hit(pos)
        if modifiers & Qt.AltModifier and node_id:
            parent = self.parent_layout_id(node_id)
            if parent:
                node_id = parent
        if node_id is None:
            page = self.index.page
            self.selected.emit([self.doc.root.id] if page.contains(pos) else [])
            return
        if modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier):
            current_ids = list(self.overlay.selection)
            if node_id in current_ids:
                current_ids.remove(node_id)
            else:
                current_ids.append(node_id)
            self.selected.emit(current_ids)
            return
        self.selected.emit([node_id])

    def _tab_click(self, pos, modifiers):
        node_id = self.hit(pos)
        node = find_node(self.doc, node_id) if node_id else None
        if not isinstance(node, Widget) or not node.object_name or self.history is None:
            return
        order = list(effective_tab_order(self.doc))
        name = node.object_name
        if name not in order:
            order.append(name)
        if modifiers & Qt.ShiftModifier:
            self.overlay.tab_next = order.index(name) + 2
            self.refresh_overlay()
            return
        position = self.overlay.tab_next - 1
        current_index = order.index(name)
        if current_index != position:
            order.pop(current_index)
            position = min(position, len(order))
            order.insert(position, name)
            self.history.execute(SetTabStops(order))
        self.overlay.tab_next = min(position + 2, len(order) + 1)
        if self.overlay.tab_next > len(order):
            self.overlay.tab_next = 1
        self.refresh_overlay()

    # -- live drags
    def _snap(self, value: float, modifiers) -> int:
        step = 1 if modifiers & Qt.AltModifier else (8 if modifiers & Qt.ShiftModifier else 4)
        return max(0, int(round(value / step) * step))

    def _live_gap(self, pos, modifiers):
        drag = self.gap_drag
        delta = (pos.y() - drag["start"].y()) if drag["vertical"] else (pos.x() - drag["start"].x())
        value = self._snap(drag["value"] + delta, modifiers)
        drag["live"] = value
        qlayout = drag["qlayout"]
        if qlayout is not None:
            setter = getattr(qlayout, "set" + drag["prop"][0].upper() + drag["prop"][1:], None)
            if setter is not None:
                setter(value)
        self.hovered.emit(f"Gap {value} px")
        self.index_dirty = True
        gap_key = drag["key"]
        self.overlay.gap_hover = {"key": gap_key}
        self.refresh_overlay()

    def _commit_gap(self):
        drag = self.gap_drag
        if drag["live"] != drag["value"] and self.history is not None:
            from spikes.form_builder.model import prop_number

            self.history.execute(SetProperty(drag["layout_id"], drag["prop"], prop_number(drag["prop"], drag["live"])))

    def _live_resize(self, pos, modifiers):
        drag = self.resize_drag
        widget = self.realization.widgets.get(drag["id"])
        if widget is None:
            return
        start = drag["start"]
        size = drag["size"]
        if "h" in drag["axis"]:
            width = max(8, self._snap(size.width() + pos.x() - start.x(), modifiers))
            widget.setFixedWidth(width)
            drag["w"] = width
        if "v" in drag["axis"]:
            height = max(8, self._snap(size.height() + pos.y() - start.y(), modifiers))
            widget.setFixedHeight(height)
            drag["h"] = height
        self.hovered.emit(f"Fixed {drag.get('w', size.width())} × {drag.get('h', size.height())}. Double-click the handle to hug again.")
        self.index_dirty = True
        self.refresh_overlay()

    def _commit_resize(self, pos, modifiers):
        drag = self.resize_drag
        node = find_node(self.doc, drag["id"])
        if not isinstance(node, Widget) or self.history is None:
            return
        default = class_default(self.doc, node.class_name)
        steps = []
        if "w" in drag:
            command = sizing.set_axis(node, "h", "fixed", default, drag["w"])
            if command is not None:
                command.redo(self.doc)
                steps.append(command)
        if "h" in drag:
            command = sizing.set_axis(node, "v", "fixed", default, drag["h"])
            if command is not None:
                command.redo(self.doc)
                steps.append(command)
        for command in reversed(steps):
            command.undo(self.doc)
        if steps:
            self.history.execute(steps[0] if len(steps) == 1 else Compound(steps))

    def _live_page(self, view_pos, modifiers):
        """Measured in view pixels: the page stays centred, so each edge moves half the change."""
        drag = self.page_drag
        width, height = drag["size"]
        scale = max(self.scale_value, 0.1)
        centred_x = 1 if self.horizontalScrollBar().isVisible() else 2
        centred_y = 1 if self.verticalScrollBar().isVisible() else 2
        if "h" in drag["axis"]:
            width = max(120, self._snap(width + (view_pos.x() - drag["start"].x()) * centred_x / scale, modifiers))
        if "v" in drag["axis"]:
            height = max(80, self._snap(height + (view_pos.y() - drag["start"].y()) * centred_y / scale, modifiers))
        drag["live"] = (width, height)
        self.form.setFixedSize(max(width, self.form.minimumSizeHint().width()), max(height, self.form.minimumSizeHint().height()))
        self.page.setFixedSize(self.form.width() + 16, self.form.height() + TITLE_STRIP + 16)
        self.host.adjustSize()
        self.scene().setSceneRect(self.proxy.boundingRect())
        self.hovered.emit(f"Window {width} × {height}. Everything in a layout follows the edge.")
        self.index_dirty = True
        self.refresh_overlay()

    def _commit_page(self, pos, modifiers):
        drag = self.page_drag
        live = drag.get("live")
        if live is None or self.history is None or live == drag["size"]:
            return
        self.history.execute(SetProperty(self.doc.root.id, "geometry", prop_rect("geometry", 0, 0, live[0], live[1])))

    # -- menus
    def _menu_click(self, menu_hit):
        kind, payload = menu_hit
        if kind == "title":
            self.overlay.menu_open = "" if self.overlay.menu_open == payload else payload
            self.selected.emit([payload])
            self.refresh_overlay()
            return
        if kind == "newmenu":
            _bar, slot, _titles = self.index.menubar
            self.editor.open(self.to_view(slot), "", lambda text, bar=payload: self._add_menu(bar, text), "Menu title")
            return
        if kind == "row":
            row = payload
            if row["kind"] == "typehere":
                menu_id = self.overlay.menu_open
                self.editor.open(self.to_view(row["rect"]), "", lambda text, menu=menu_id: self._add_action(menu, text), "Action text, or - for a separator")
            elif row.get("id"):
                self.selected.emit([row["id"]])
            self.refresh_overlay()

    def _add_menu(self, bar_id: str, text: str):
        text = text.strip()
        if not text or self.history is None:
            return
        from spikes.form_builder.commands import add_menu_command

        command, menu_id = add_menu_command(self.doc, bar_id, text)
        self.history.execute(command)
        self.overlay.menu_open = menu_id
        self.selected.emit([menu_id])

    def _add_action(self, menu_id: str, text: str):
        text = text.strip()
        if not text or self.history is None:
            return
        from spikes.form_builder.commands import add_action_command

        command, action_id = add_action_command(self.doc, menu_id, text)
        self.history.execute(command)
        self.overlay.menu_open = menu_id
        if action_id:
            self.selected.emit([action_id])

    def keyPressEvent(self, event):
        # Arrows walk the selection and Enter goes into a container; the window handles both.
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)

    # -- palette drops
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME) and self.overlay.mode == "design":
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(MIME) or self.doc is None:
            event.ignore()
            return
        if self.index_dirty:
            self.rebuild_index()
        _kind, class_name = bytes(event.mimeData().data(MIME)).decode("utf-8").split(":", 1)
        pos = self.host_pos(event.position().toPoint())
        self.overlay.slot = self.slot_at(pos, class_name)
        self.hovered.emit(self.overlay.slot.label if self.overlay.slot else "No layout here. Drop inside the window.")
        self.refresh_overlay()
        if self.overlay.slot is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.doc is None or self.history is None:
            return
        raw = bytes(event.mimeData().data(MIME)).decode("utf-8")
        kind, class_name = raw.split(":", 1)
        entry = Entry(class_name, class_name, kind, "")
        pos = self.host_pos(event.position().toPoint())
        slot = self.overlay.slot or self.slot_at(pos, class_name)
        self.overlay.slot = None
        if slot is not None:
            content = content_for(self.doc, entry)
            command = self.commands_for_drop(content, slot)
            if command is not None:
                self.history.execute(command)
                self.selected.emit([content.id])
        self.refresh_overlay()
        event.acceptProposedAction()

    def dragLeaveEvent(self, _event):
        self.overlay.slot = None
        self.hovered.emit("")
        self.refresh_overlay()


# --------------------------------------------------------------------------- canvas
class Canvas(QWidget):
    selection_changed = Signal(list)
    status_text = Signal(str)
    timed = Signal(str, float)
    context_requested = Signal(QPoint)
    text_edit_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.primary = Surface("primary")
        self.secondary = Surface("secondary")
        self.secondary.hide()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        row.addWidget(self.primary)
        row.addWidget(self.secondary)
        self.two_widths = False
        self.primary_zoom = 1.0
        self.doc = None
        self.history = None
        self.selection: list[str] = []
        self.mode = "design"
        for surface in (self.primary, self.secondary):
            surface.selected.connect(self._on_selected)
            surface.hovered.connect(self.status_text)
            surface.context.connect(self.context_requested)
            surface.edit_text.connect(self.text_edit_requested)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_after_edit)

    def surfaces(self):
        return [self.primary, self.secondary] if self.two_widths else [self.primary]

    def set_document(self, doc, history):
        started = time.perf_counter()
        self.doc = doc
        self.history = history
        self.selection = []
        for surface in (self.primary, self.secondary):
            surface.overlay.selection = []
            surface.overlay.hover = None
            surface.overlay.slot = None
            surface.overlay.menu_open = ""
        self.primary.set_document(doc, history)
        if self.two_widths:
            self.secondary.set_document(doc, history)
        self.timed.emit("open", (time.perf_counter() - started) * 1000)
        self._sync_tab_badges()

    def on_command(self, command):
        started = time.perf_counter()
        structural = _is_structural(command)
        for surface in self.surfaces():
            if surface.form is None:
                surface.rebuild()
            elif structural:
                if not surface.realization.reconcile():
                    surface.rebuild()
            else:
                _apply_light(surface, command)
            surface.apply_size()
            surface.index_dirty = True
        self.timed.emit("edit", (time.perf_counter() - started) * 1000)
        self.selection = [node_id for node_id in self.selection if find_node(self.doc, node_id) is not None]
        self._sync_tab_badges()
        self._refresh_timer.start(0)

    def _refresh_after_edit(self):
        for surface in self.surfaces():
            surface.overlay.selection = list(self.selection)
            surface.refresh_overlay()

    def set_selection(self, ids):
        self.selection = list(ids)
        for surface in (self.primary, self.secondary):
            surface.overlay.selection = list(ids)
            if surface.overlay.menu_open and not any(_belongs_to_menu(self.doc, node_id, surface.overlay.menu_open) for node_id in ids):
                surface.overlay.menu_open = ""
            surface.refresh_overlay()

    def set_mode(self, mode: str):
        self.mode = mode
        for surface in (self.primary, self.secondary):
            surface.overlay.mode = mode
            surface.overlay.tab_next = 1
            surface.overlay.menu_open = ""
        self._sync_tab_badges()
        for surface in self.surfaces():
            surface.refresh_overlay()

    def set_tokens(self, tokens):
        self.primary.set_tokens(tokens)
        self.secondary.set_tokens(tokens)

    def set_zoom(self, value: float):
        self.primary_zoom = value
        for surface in self.surfaces():
            surface.fit = False
            surface.set_scale(value)

    def set_text_size(self, point_size: float):
        self.primary.set_text_size(point_size)
        self.secondary.set_text_size(point_size)

    def set_two_widths(self, enabled: bool):
        self.two_widths = enabled
        self.secondary.setVisible(enabled)
        if enabled and self.doc is not None:
            self.secondary.set_document(self.doc, self.history)
            self.secondary.overlay.mode = self.mode
            self.secondary.overlay.selection = list(self.selection)
            self.primary.set_preview_width(420)
            self.secondary.set_preview_width(760)
            self.primary.overlay.header = "Narrow · 420 px"
            self.secondary.overlay.header = "Wide · 760 px"
            for surface in (self.primary, self.secondary):
                surface.fit = True
                QTimer.singleShot(0, surface.fit_width)
        else:
            self.primary.overlay.header = ""
            self.primary.fit = False
            self.primary.set_preview_width(0)
            self.primary.set_scale(self.primary_zoom)
        self._sync_tab_badges()

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


def _cell(qlayout, row, column):
    """Union of a grid row's (or column's) cell rectangles; None when Qt has none yet."""
    rect = None
    count = qlayout.columnCount() if row is not None else qlayout.rowCount()
    for other in range(count):
        cell = qlayout.cellRect(row, other) if row is not None else qlayout.cellRect(other, column)
        if cell.isValid() and not cell.isEmpty():
            rect = cell if rect is None else rect.united(cell)
    return rect


def _belongs_to_menu(doc, node_id: str, menu_id: str) -> bool:
    if node_id == menu_id:
        return True
    node = find_node(doc, node_id)
    menu = find_node(doc, menu_id)
    if isinstance(node, Action) and isinstance(menu, Widget):
        return any(isinstance(part, ActionRef) and part.name == node.name for part in menu.body)
    return False


def _is_structural(command) -> bool:
    from spikes.form_builder.commands import Rename, SetAttribute, SetLayoutAttrib, SetProperties

    if isinstance(command, (SetProperty, SetProperties, Rename, SetTabStops)):
        return False
    if isinstance(command, (SetAttribute, SetLayoutAttrib)):
        return True
    if isinstance(command, Compound):
        return any(_is_structural(step) for step in command.steps)
    return True


def _apply_light(surface: Surface, command) -> None:
    from spikes.form_builder.commands import Rename, SetProperties

    if isinstance(command, SetProperty):
        node = find_node(surface.doc, command.node_id)
        if isinstance(node, Action) or (isinstance(node, Widget) and node.class_name in ("QMenu", "QMenuBar", "QToolBar")):
            surface.rebuild()
            return
        surface.realization.apply_node_property(command.node_id, command.name)
    elif isinstance(command, SetProperties):
        for step in command.steps:
            surface.realization.apply_node_property(step.node_id, step.name)
    elif isinstance(command, Rename):
        node = find_node(surface.doc, command.node_id)
        widget = surface.realization.widgets.get(command.node_id)
        if isinstance(node, Widget) and widget is not None:
            widget.setObjectName(node.object_name)
        elif isinstance(node, Layout):
            qlayout = surface.realization.layouts.get(node.id)
            if qlayout is not None:
                qlayout.setObjectName(node.object_name)


# --------------------------------------------------------------------------- content
def drop_entry(doc, history, entry: Entry, slot) -> None:
    """Older entry point: insert an entry at a slot dict (layout_id, index, attrib, widget_id)."""
    content = content_for(doc, entry)
    if isinstance(slot, Slot):
        surface_slot = slot
    elif slot.get("layout_id"):
        surface_slot = Slot("cell" if slot.get("attrib") else "insert", slot["layout_id"], slot.get("index", 0), attrib=slot.get("attrib") or {})
    elif slot.get("widget_id"):
        surface_slot = Slot("newlayout", widget_id=slot["widget_id"])
    else:
        return
    if surface_slot.mode == "newlayout":
        layout_id = doc.alloc()
        history.execute(
            Compound(
                [
                    EnsureLayout(surface_slot.widget_id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                    InsertItem(layout_id, 0, make_item(doc, content)),
                ]
            )
        )
        return
    index = surface_slot.index if surface_slot.mode == "insert" else 10**6
    history.execute(with_tab_splice(doc, InsertItem(surface_slot.layout_id, index, make_item(doc, content, **surface_slot.attrib)), content))


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
        words = {"QPushButton": "Button", "QToolButton": "...", "QCheckBox": "Check box", "QRadioButton": "Option"}
        widget.body.append(prop_string("text", words[entry.class_name]))
    elif entry.class_name == "QGroupBox":
        widget.body.append(prop_string("title", "Group"))
        widget.body.append(make_layout(doc, "QVBoxLayout"))
    elif entry.class_name == "QFrame":
        widget.body.append(prop_enum("frameShape", "QFrame::StyledPanel"))
        widget.body.append(make_layout(doc, "QVBoxLayout"))
    elif entry.class_name == "QTabWidget":
        for number in (1, 2):
            page = make_widget(doc, "QWidget", unique_name(doc, "tab"))
            set_attribute(page, "title", f"Tab {number}")
            page.body.append(make_layout(doc, "QVBoxLayout"))
            widget.body.append(page)
    elif entry.class_name == "QStackedWidget":
        page = make_widget(doc, "QWidget", unique_name(doc, "page"))
        page.body.append(make_layout(doc, "QVBoxLayout"))
        widget.body.append(page)
    elif entry.class_name == "QScrollArea":
        widget.body.append(_bool("widgetResizable", True))
        page = make_widget(doc, "QWidget", unique_name(doc, "scrollAreaWidgetContents"))
        page.body.append(make_layout(doc, "QVBoxLayout"))
        widget.body.append(page)
    elif entry.class_name == "QSplitter":
        widget.body.append(prop_enum("orientation", "Qt::Horizontal"))
    elif entry.class_name == "QDialogButtonBox":
        widget.body.append(prop_set("standardButtons", "QDialogButtonBox::Cancel|QDialogButtonBox::Ok"))
    return widget


def _bool(name, value):
    from spikes.form_builder.model import prop_bool

    return prop_bool(name, value)


def item_for(doc, content, attrib: dict):
    return make_item(doc, content, **attrib)


def start_drag(widget: QWidget, entry: Entry) -> None:
    mime = QMimeData()
    mime.setData(MIME, f"{entry.kind}:{entry.class_name}".encode("utf-8"))
    drag = QDrag(widget)
    drag.setMimeData(mime)
    from spikes.form_builder.icons import pixmap

    drag.setPixmap(pixmap(entry.class_name if entry.kind != "spacer" else entry.class_name, current().accent, 24))
    drag.exec(Qt.CopyAction)
