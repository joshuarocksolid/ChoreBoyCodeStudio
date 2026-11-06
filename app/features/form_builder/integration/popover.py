"""Small form popovers. They are not window-modal dialogs."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from app.qt.QtCore import QPoint, QRect, QSize, Qt
from app.qt.QtGui import QColor, QPainter, QPen, QPixmap
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.layout_actions import KINDS, SEGMENTS, ApplyKind, OfferSheet, gate
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.layout_gestures import beside
from app.features.form_builder.qtside.theme.chrome import FormChrome, apply_page_shadow
from app.features.form_builder.qtside.theme.metrics import ICON, R_POPOVER, ROW, S2

_LAYOUT_GLYPH = {
    "vertical": "layout_v",
    "horizontal": "layout_h",
    "grid": "layout_grid",
    "form": "layout_form",
}
_LAYOUT_WIDTH = 220


class ProblemPopover(QFrame):
    """The problem text when the Problems panel cannot show the row."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.problemPopover")
        self.setAccessibleName("Problem")
        self.setFocusPolicy(_no_focus())
        self.setMaximumWidth(480)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        self._text = QLabel(self)
        self._text.setObjectName("formBuilder.problemText")
        self._text.setWordWrap(True)
        self._text.setFocusPolicy(_no_focus())
        row.addWidget(self._text, 1)
        self.hide()

    def show_message(self, text: str) -> None:
        self._text.setText(text)
        self._text.setAccessibleName(text)
        self.show()
        self.raise_()
        self.place()

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        width = min(480, max(self.sizeHint().width(), 160), max(1, parent.width() - 16))
        height = max(self.sizeHint().height(), 28)
        self.resize(width, height)
        self.move(max(0, (parent.width() - width) // 2), max(0, parent.height() - height - 16))


class _LayoutMenu(QMenu):
    """Four layout rows. Painted here so a popup grab is not an empty native menu."""

    def __init__(self, parent: QWidget, chrome: Optional[FormChrome]) -> None:
        super().__init__(parent)
        self._chrome = chrome
        self._icons: Dict[str, QPixmap] = {}
        self.setObjectName("formBuilder.layoutPopover")
        self.setToolTipsVisible(True)
        self.setFixedSize(_LAYOUT_WIDTH, S2 * 2 + ROW * len(SEGMENTS))
        if chrome is None:
            return
        edge = chrome.popup_border or chrome.border
        fill = chrome.popup or chrome.panel
        self.setStyleSheet(
            "QMenu#formBuilder\\.layoutPopover { background: %s; color: %s;"
            " border: 1px solid %s; border-radius: %dpx; }"
            "QMenu#formBuilder\\.layoutPopover::item { padding: 0px; background: transparent; }"
            % (fill, chrome.text, edge, R_POPOVER)
        )
        apply_page_shadow(self, is_dark=chrome.is_dark, is_high_contrast=chrome.is_high_contrast)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_LAYOUT_WIDTH, S2 * 2 + ROW * len(SEGMENTS))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        chrome = self._chrome
        if chrome is None:
            super().paintEvent(event)  # type: ignore[arg-type]
            return
        painter = QPainter(self)
        fill = QColor(chrome.popup or chrome.panel)
        edge = QColor(chrome.popup_border or chrome.border)
        painter.setPen(getattr(getattr(Qt, "PenStyle", Qt), "NoPen"))
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rect(), R_POPOVER, R_POPOVER)
        pen = QPen(edge)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), R_POPOVER, R_POPOVER)
        chosen = QColor(chrome.selected or chrome.row_hover)
        active = self.activeAction()
        align = enum_value(Qt.AlignmentFlag.AlignVCenter) | enum_value(Qt.AlignmentFlag.AlignLeft)
        top = S2
        for action in self.actions():
            if action.isSeparator():
                continue
            row = QRect(S2, top, self.width() - S2 * 2, ROW)
            if action is active and action.isEnabled():
                painter.fillRect(row, chosen)
            painter.setPen(QColor(chrome.text if action.isEnabled() else chrome.muted))
            glyph = self._icons.get(str(action.data() or ""))
            text = row
            if glyph is not None and not glyph.isNull():
                painter.drawPixmap(row.x(), row.y() + max(0, (ROW - ICON) // 2), glyph)
                text = row.adjusted(ICON + S2, 0, 0, 0)
            painter.drawText(text, align, action.text())
            top += ROW
        painter.end()

    def _remember(self, kind_id: str, color: str) -> None:
        ratio = getattr(self, "devicePixelRatioF", None)
        dpr = float(ratio()) if callable(ratio) else 1.0
        self._icons[kind_id] = paint_glyph(_LAYOUT_GLYPH[kind_id], color, ICON, dpr)


def open_layout_menu(
    parent: QWidget,
    sheet: OfferSheet,
    run: Callable[[object], None],
    at: object,
    chrome: object = None,
) -> QMenu:
    """A non-blocking menu of the four layouts. Disabled rows carry the reason as a tooltip."""
    themed = chrome if isinstance(chrome, FormChrome) else None
    menu = _LayoutMenu(parent, themed)
    ink = ""
    if themed is not None:
        ink = themed.icon_muted or themed.muted
    for kind_id in SEGMENTS:
        request = ApplyKind(kind_id)
        offer = gate(sheet, request)
        action = menu.addAction(KINDS[kind_id].label)
        action.setData(kind_id)
        action.setEnabled(offer.enabled)
        if offer.reason:
            action.setToolTip(offer.reason)
        action.triggered.connect(lambda _checked=False, request=request: run(request))
        if ink and kind_id in _LAYOUT_GLYPH:
            menu._remember(kind_id, ink)  # noqa: SLF001
    current = next((action for action in menu.actions() if action.isEnabled()), None)
    if current is not None:
        menu.setActiveAction(current)
    _place_layout_menu(menu, parent, at)
    return menu


def _place_layout_menu(menu: QMenu, parent: QWidget, at: object) -> None:
    """Sit the menu beside the widget the chip belongs to, inside the canvas."""
    spot = at if isinstance(at, QPoint) else QPoint(0, 0)
    canvas = parent.findChild(QWidget, "formBuilder.canvas")
    if canvas is None or not hasattr(canvas, "viewport"):
        menu.popup(spot)
        return
    viewport = canvas.viewport()
    origin = viewport.mapToGlobal(QPoint(0, 0))
    bounds = QRect(origin, viewport.size())
    subject = _widget_rect(canvas, parent, spot, origin)
    if subject is None:
        subject = QRect(spot, QSize(1, 1))
    menu.adjustSize()
    menu.resize(menu.sizeHint())
    placed = beside(subject, menu.sizeHint(), bounds)
    menu.popup(placed)
    menu.resize(menu.sizeHint())
    menu.move(placed)


def _widget_rect(canvas: QWidget, parent: QWidget, at: QPoint, origin: QPoint) -> Optional[QRect]:
    node = _node_at_chip(canvas, at)
    if node is None:
        session = getattr(parent, "session", None)
        selection = getattr(session, "selection", None)
        state = getattr(selection, "state", None)
        node = getattr(state, "current", None)
    drawn = canvas.viewport_rect((node,)) if node is not None and hasattr(canvas, "viewport_rect") else None
    if drawn is None or drawn.width() <= 0 or drawn.height() <= 0:
        return None
    return QRect(origin.x() + drawn.x(), origin.y() + drawn.y(), drawn.width(), drawn.height())


def _node_at_chip(canvas: QWidget, at: QPoint) -> object:
    frame = canvas.overlay() if hasattr(canvas, "overlay") else None
    chips = getattr(frame, "chips", ())
    for rect, node in chips:
        local = canvas.mapFromScene(float(rect.x), float(rect.y + rect.height))  # type: ignore[attr-defined]
        point = canvas.mapToGlobal(QPoint(int(local.x()), int(local.y())))
        if abs(point.x() - at.x()) <= 3 and abs(point.y() - at.y()) <= 3:
            return node
    return None


def tree_contains(tree: QWidget, text: str) -> bool:
    """True when any row shows ``text``."""
    role_count = getattr(tree, "columnCount", None)
    columns = role_count() if callable(role_count) else 1
    root = getattr(tree, "invisibleRootItem", None)
    if not callable(root):
        return False
    return _walk(root(), text, max(1, int(columns)))


def _walk(item: object, text: str, columns: int) -> bool:
    reader = getattr(item, "text", None)
    if callable(reader):
        for column in range(columns):
            if text and text in str(reader(column)):
                return True
    count = getattr(item, "childCount", None)
    child = getattr(item, "child", None)
    if not callable(count) or not callable(child):
        return False
    for index in range(count()):
        found = child(index)
        if found is not None and _walk(found, text, columns):
            return True
    return False


def _no_focus() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
