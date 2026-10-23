"""Design canvas (UX-WB-004).

The realized form sits in a proxy on the runtime scene. Chip, size, grabbers
and the toast are chrome on the view, so a theme change does not restyle the
page. Nothing on the canvas selects or drags in this slice.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

from app.qt.QtCore import QEvent, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)
from app.qt.qt_compat import enum_value, wrapper_is_valid

from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.integration.chrome_text import page_chip_label, page_size_text, window_title
from app.features.form_builder.integration.layout import GUTTER
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import (
    TITLE_BAR,
    ChromeKind,
    ChromeTokens,
    DOT_SIZE_PX,
    DOT_STEP_PX,
    Elevation,
    Height,
    Radius,
    Space,
    backdrop_of,
    chrome_tokens,
    elevation,
    font_css,
)
from app.features.form_builder.qtside.theme.runtime import (
    isolate_scene,
    restore_authored_fonts,
    startup_font,
)
from app.shell.theme_tokens import ShellThemeTokens

_DETACH_BEFORE_REALIZE = 9
_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)")
_SHADOW_PAD = 24


def _focus_policy() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "StrongFocus")


def _no_focus() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "NoFocus")


def _transparent() -> Qt.WidgetAttribute:
    attrs = getattr(Qt, "WidgetAttribute", Qt)
    return getattr(attrs, "WA_TransparentForMouseEvents")


def _qt(owner: object, group: str, name: str) -> object:
    return getattr(getattr(owner, group, owner), name)


def _token_color(value: str) -> QColor:
    match = _RGBA.fullmatch(value.strip())
    if match is None:
        return QColor(value)
    red, green, blue, alpha = match.groups()
    color = QColor(int(red), int(green), int(blue))
    color.setAlphaF(float(alpha))
    return color


class FormCanvas(QGraphicsView):
    """Dot grid, centred page, and the chrome around it."""

    def __init__(self, session: FormSession, realizer: Realizer, parent: QWidget) -> None:
        super().__init__(parent)
        self._session = session
        self._realizer = realizer
        self._chrome: Optional[ChromeTokens] = None
        self._window_title = ""
        self._shadow_key: Optional[Tuple[object, ...]] = None
        self._shadow_pixmap: Optional[QPixmap] = None
        self._banner_push = 0
        self._closer: Optional[Callable[[], None]] = None
        self.setObjectName("formBuilder.canvas")
        self.setAccessibleName("Form canvas")
        self.setFocusPolicy(_focus_policy())
        shape = getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")
        self.setFrameShape(shape)
        drag = getattr(QGraphicsView, "DragMode", QGraphicsView)
        self.setDragMode(getattr(drag, "NoDrag"))
        self.setInteractive(False)
        scene = QGraphicsScene(self)
        isolate_scene(scene)
        self.setScene(scene)
        self._proxy = QGraphicsProxyWidget()
        scene.addItem(self._proxy)
        # setWidget(None) drops the proxy's hold without deleting the widget.
        # The realizer deletes the old root on a replace. Detach first.
        self._detach_sub = session.log.subscribe(self._detach_for_replace, priority=_DETACH_BEFORE_REALIZE)
        self._view_sub = session.log.subscribe(self._sync_root, priority=PRIORITY_VIEWS)
        root = realizer.build()
        self._proxy.setWidget(root)
        self._build_chrome()
        self.viewport().installEventFilter(self)
        self.horizontalScrollBar().valueChanged.connect(self._position_chrome)
        self.verticalScrollBar().valueChanged.connect(self._position_chrome)
        self._refresh_chip()
        self._place_page()

    def page_widget(self) -> Optional[QWidget]:
        root = self._realizer.root_widget
        if root is None or not wrapper_is_valid(root):
            return None
        return root

    def set_drawer_closer(self, callback: Callable[[], None]) -> None:
        self._closer = callback

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Chrome only. The page palette stays the runtime palette."""
        chrome = chrome_tokens(tokens)
        self._chrome = chrome
        self._shadow_key = None
        self._shadow_pixmap = None
        card = elevation(2, chrome)
        # Level 2 is 2 px only in high contrast, where the stroke is text.
        stroke = chrome.paint("text", "popup") if card.border_px >= 2 else chrome.popup_border
        self.setStyleSheet(
            "QGraphicsView#formBuilder\\.canvas {"
            " background: %s; border: 1px solid %s; }"
            "QGraphicsView#formBuilder\\.canvas:focus { border: %dpx solid %s; }"
            "QLabel#formBuilder\\.name {"
            " color: %s; background: %s; border: 1px solid %s; border-radius: %dpx;"
            " padding: %dpx %dpx; %s }"
            "QLabel#formBuilder\\.sizeReadout {"
            " color: %s; background: transparent; border: none; padding: 0; %s }"
            "QWidget#formBuilder\\.grabberRight, QWidget#formBuilder\\.grabberBottom {"
            " background: %s; border: none; border-radius: %dpx; }"
            "QLabel#formBuilder\\.toast {"
            " color: %s; background: %s; border: %dpx solid %s; border-radius: %dpx;"
            " padding: %dpx %dpx; }"
            % (
                chrome.backdrop,
                chrome.border,
                chrome.focus_width,
                chrome.paint("accent", "backdrop"),
                chrome.paint("text", "panel"),
                chrome.panel,
                chrome.border,
                int(Radius.CONTROL),
                int(Space.XS),
                int(Space.S),
                font_css(chrome.scale.chip(), lock_weight=True),
                chrome.paint("muted", "backdrop"),
                font_css(chrome.scale.caption),
                chrome.paint("faint", "backdrop"),
                int(Radius.CONTROL),
                chrome.paint("text", "popup"),
                chrome.popup,
                card.border_px,
                stroke,
                int(Radius.POPOVER),
                int(Space.XS),
                int(Space.S),
            )
        )
        self.viewport().update()
        self._position_chrome()
        # The shell sets the tooltip sheet, then this theme. That polish
        # drops authored fonts on stylesheet widgets. Put them back.
        page = self.page_widget()
        if page is not None:
            restore_authored_fonts(page)

    def refresh_chip(self) -> None:
        self._refresh_chip()
        self._place_page()

    def detach(self) -> None:
        widget = self._proxy.widget()
        if widget is not None:
            self._proxy.setWidget(None)

    def dispose(self) -> None:
        self._detach_sub.close()
        self._view_sub.close()
        self.detach()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        press = getattr(getattr(QEvent, "Type", QEvent), "MouseButtonPress", None)
        if press is None:
            press = getattr(QEvent, "MouseButtonPress", None)
        if watched is self.viewport() and press is not None and event.type() == press:
            closer = self._closer
            if closer is not None:
                closer()
        return False

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._place_page()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        backdrop, dots = self._backdrop()
        painter.fillRect(rect, QColor(backdrop))
        self._paint_dots(painter, rect, dots)
        self._paint_page_card(painter)

    def _backdrop(self) -> Tuple[str, str]:
        chrome = self._chrome
        if chrome is None:
            return backdrop_of(ChromeKind.LIGHT)
        return chrome.backdrop, chrome.dots

    def _paint_dots(self, painter: QPainter, rect: QRectF, dots: str) -> None:
        if not dots:
            return
        painter.save()
        painter.setRenderHint(_qt(QPainter, "RenderHint", "Antialiasing"), False)
        painter.setPen(_qt(Qt, "PenStyle", "NoPen"))
        painter.setBrush(QColor(dots))
        left = int(rect.left()) - (int(rect.left()) % DOT_STEP_PX)
        top = int(rect.top()) - (int(rect.top()) % DOT_STEP_PX)
        right = int(rect.right()) + DOT_STEP_PX
        bottom = int(rect.bottom()) + DOT_STEP_PX
        y = top
        while y < bottom:
            x = left
            while x < right:
                painter.drawRect(x, y, DOT_SIZE_PX, DOT_SIZE_PX)
                x += DOT_STEP_PX
            y += DOT_STEP_PX
        painter.restore()

    def _paint_page_card(self, painter: QPainter) -> None:
        page = self._page_scene_rect()
        if page is None:
            return
        card = QRectF(page.left(), page.top() - TITLE_BAR.height, page.width(), page.height() + TITLE_BAR.height)
        chrome = self._chrome
        if chrome is not None:
            self._paint_page_shadow(painter, card, elevation(1, chrome))
        self._paint_title_bar(painter, card)
        if chrome is None:
            return
        level = elevation(1, chrome)
        if level.border_px <= 0:
            return
        painter.save()
        pen = QPen(QColor(chrome.paint("text", "backdrop")))
        pen.setWidth(level.border_px)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(_qt(Qt, "BrushStyle", "NoBrush"))
        painter.drawRoundedRect(card, float(Radius.PAGE), float(Radius.PAGE))
        painter.restore()

    def _page_scene_rect(self) -> Optional[QRectF]:
        widget = self._proxy.widget()
        if widget is None or not wrapper_is_valid(widget):
            return None
        rect = self._proxy.sceneBoundingRect()
        if rect.isEmpty():
            return None
        return rect

    def _paint_page_shadow(self, painter: QPainter, card: QRectF, level: Elevation) -> None:
        if not level.shadows:
            return
        pixmap = self._shadow_for(card, level)
        if pixmap is None:
            return
        painter.drawPixmap(int(card.left()) - _SHADOW_PAD, int(card.top()) - _SHADOW_PAD, pixmap)

    def _shadow_for(self, card: QRectF, level: Elevation) -> Optional[QPixmap]:
        key = (
            int(card.width()),
            int(card.height()),
            tuple((shadow.x, shadow.y, shadow.blur, shadow.color) for shadow in level.shadows),
        )
        if key == self._shadow_key and self._shadow_pixmap is not None:
            return self._shadow_pixmap
        width = int(card.width()) + _SHADOW_PAD * 2
        height = int(card.height()) + _SHADOW_PAD * 2
        if width <= 0 or height <= 0:
            return None
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(0, 0, 0, 0))
        shadow_painter = QPainter(pixmap)
        shadow_painter.setRenderHint(_qt(QPainter, "RenderHint", "Antialiasing"), True)
        shadow_painter.setPen(_qt(Qt, "PenStyle", "NoPen"))
        for shadow in level.shadows:
            color = _token_color(shadow.color)
            steps = max(shadow.blur, 1)
            step = steps
            while step > 0:
                layer = QColor(color)
                layer.setAlphaF(min(1.0, color.alphaF() * (steps - step + 1) / (steps * steps)))
                shadow_painter.setBrush(layer)
                rect = QRectF(
                    _SHADOW_PAD + shadow.x - step,
                    _SHADOW_PAD + shadow.y - step,
                    card.width() + step * 2,
                    card.height() + step * 2,
                )
                radius = float(Radius.PAGE) + step
                shadow_painter.drawRoundedRect(rect, radius, radius)
                step -= 1
        shadow_painter.end()
        self._shadow_key = key
        self._shadow_pixmap = pixmap
        return pixmap

    def _paint_title_bar(self, painter: QPainter, card: QRectF) -> None:
        bar = QRectF(card.left(), card.top(), card.width(), TITLE_BAR.height)
        painter.save()
        painter.setRenderHint(_qt(QPainter, "RenderHint", "Antialiasing"), True)
        clip = QPainterPath()
        clip.addRoundedRect(card, float(Radius.PAGE), float(Radius.PAGE))
        painter.setClipPath(clip)
        painter.fillRect(bar, QColor(TITLE_BAR.fill))
        font = QFont(startup_font())
        font.setPixelSize(TITLE_BAR.title_px)
        # Qt 5 setWeight takes the 0-99 scale. DemiBold is CSS 600.
        font.setWeight(_qt(QFont, "Weight", "DemiBold"))
        painter.setFont(font)
        painter.setPen(QColor(TITLE_BAR.glyph))
        marks = TITLE_BAR.marks
        glyph_w = int(Space.L)
        glyphs_w = glyph_w * len(marks)
        text_rect = QRectF(bar.left() + int(Space.S), bar.top(), max(0, bar.width() - glyphs_w - int(Space.S) * 2), bar.height())
        elide = _qt(Qt, "TextElideMode", "ElideRight")
        shown = painter.fontMetrics().elidedText(self._window_title, elide, int(text_rect.width()))
        align = enum_value(_qt(Qt, "AlignmentFlag", "AlignLeft")) | enum_value(
            _qt(Qt, "AlignmentFlag", "AlignVCenter")
        )
        painter.drawText(text_rect, align, shown)
        index = 0
        for mark in marks:
            cell = QRectF(bar.right() - glyphs_w - int(Space.S) + index * glyph_w, bar.top(), glyph_w, bar.height())
            painter.drawText(cell, _qt(Qt, "AlignmentFlag", "AlignCenter"), mark)
            index += 1
        painter.restore()

    def _build_chrome(self) -> None:
        self._name = QLabel(self)
        self._name.setObjectName("formBuilder.name")
        self._name.setAccessibleName("Form name")
        self._size = QLabel(self)
        self._size.setObjectName("formBuilder.sizeReadout")
        self._size.setAccessibleName("Page size")
        self._grabber_right = QWidget(self)
        self._grabber_right.setObjectName("formBuilder.grabberRight")
        self._grabber_right.setFocusPolicy(_no_focus())
        self._grabber_right.setAttribute(_transparent(), True)
        self._grabber_right.resize(4, 32)
        self._grabber_bottom = QWidget(self)
        self._grabber_bottom.setObjectName("formBuilder.grabberBottom")
        self._grabber_bottom.setFocusPolicy(_no_focus())
        self._grabber_bottom.setAttribute(_transparent(), True)
        self._grabber_bottom.resize(32, 4)
        self._toast = QLabel(self)
        self._toast.setObjectName("formBuilder.toast")
        self._toast.setAccessibleName("Notice")
        self._toast.hide()

    def _detach_for_replace(self, changeset: ChangeSet) -> None:
        if changeset.replaced:
            self.detach()

    def _sync_root(self, _changeset: ChangeSet) -> None:
        root = self._realizer.root_widget
        if root is None:
            return
        current = self._proxy.widget()
        if current is not root:
            if current is not None and wrapper_is_valid(current):
                self._proxy.setWidget(None)
            self._proxy.setWidget(root)
        self._refresh_chip()
        self._place_page()

    def _refresh_chip(self) -> None:
        document = self._session.document
        label = page_chip_label(document, "Form")
        self._name.setText(label)
        self._name.setAccessibleName(label)
        self._window_title = window_title(document)
        self.viewport().update()
        self._size.setText(self._size_text(document))
        self._position_chrome()

    def _size_text(self, document: UiDocument) -> str:
        authored = page_size_text(document)
        if authored:
            return authored
        root = self.page_widget()
        if root is None:
            return ""
        hint = root.sizeHint()
        width = hint.width() if hint.width() > 0 else root.width()
        height = hint.height() if hint.height() > 0 else root.height()
        if width <= 0 or height <= 0:
            return ""
        return "%d × %d" % (width, height)

    def _place_page(self) -> None:
        root = self._proxy.widget()
        if root is None or not wrapper_is_valid(root):
            return
        hint = root.sizeHint()
        width = hint.width() if hint.width() > 0 else max(root.width(), 320)
        height = hint.height() if hint.height() > 0 else max(root.height(), 240)
        root.resize(width, height)
        view_w = max(self.viewport().width(), width + GUTTER * 2)
        view_h = max(self.viewport().height(), height + GUTTER * 2)
        self.scene().setSceneRect(0, 0, view_w, view_h)
        x = max(GUTTER, (view_w - width) // 2)
        y = max(GUTTER, (view_h - height) // 2) + self._banner_push
        self._proxy.setPos(x, y)
        self._position_chrome()

    def _position_chrome(self) -> None:
        if self._proxy.widget() is None:
            return
        rect = self._proxy.sceneBoundingRect()
        top_left = self.mapFromScene(rect.topLeft())
        bottom_right = self.mapFromScene(rect.bottomRight())
        self._fit_label(self._name)
        self._fit_label(self._size)
        self._name.move(
            top_left.x(),
            max(0, top_left.y() - TITLE_BAR.height - self._name.height() - int(Space.XS)),
        )
        self._name.raise_()
        size_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - self._size.width()) // 2)
        self._size.move(size_x, bottom_right.y() + int(Space.S))
        self._size.raise_()
        mid_y = top_left.y() + max(0, (bottom_right.y() - top_left.y() - 32) // 2)
        self._grabber_right.move(bottom_right.x() + 2, mid_y)
        self._grabber_right.raise_()
        mid_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - 32) // 2)
        self._grabber_bottom.move(mid_x, bottom_right.y() + 2)
        self._grabber_bottom.raise_()
        self._place_toast()

    def _fit_label(self, label: QLabel) -> None:
        text = label.text()
        width = label.fontMetrics().horizontalAdvance(text) + int(Space.L)
        height = max(int(Height.CONTROL), label.fontMetrics().height() + int(Space.S))
        label.setFixedSize(max(width, 8), height)

    def _place_toast(self) -> None:
        if self._toast.isVisible():
            self._toast.adjustSize()
            toast_x = max(0, (self.width() - self._toast.width()) // 2)
            self._toast.move(toast_x, self.height() - self._toast.height() - int(Space.L))


__all__ = ["FormCanvas"]
