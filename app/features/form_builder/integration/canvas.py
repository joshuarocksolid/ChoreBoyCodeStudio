"""Design canvas (UX-WB-004).

The realized form sits in a proxy on the runtime scene. The controller owns
selection, hover and gestures. ``drawForeground`` paints the overlay frame.
The page caption, shadow and toast stay view chrome.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.qt.QtCore import QEvent, QPoint, QRectF, Qt, QTimer
from app.qt.QtGui import QColor, QFont, QPainter, QPen
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid

from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX, PRIORITY_VIEWS
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex
from app.features.form_builder.engine.query.slots import DropPaint, PageControl, Point
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.chrome_text import page_title_text
from app.features.form_builder.qtside.canvas.controller import CanvasController, CanvasHost
from app.features.form_builder.qtside.canvas.core.frame import Chip, OverlayFrame
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect
from app.features.form_builder.qtside.canvas.core.gesture import HostEvent
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.canvas.paint import paint_docked_chip, paint_frame
from app.features.form_builder.qtside.canvas.stage import Stage, visible_scene_rect
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import (
    PAGE_TITLE_FILL,
    PAGE_TITLE_GLYPH,
    PAGE_TITLE_HEIGHT,
    PAGE_TITLE_TEXT,
    backdrop_colors,
    on_accent_for,
    page_shadow_rgba,
)
from app.features.form_builder.qtside.theme.overlay import (
    BackdropPalette,
    CanvasPalette,
    overlay_palette,
)
from app.features.form_builder.qtside.theme.runtime import isolate_scene, startup_font
from app.shell.theme_tokens import ShellThemeTokens

_DOT = 16


def _keep_claimed_shortcut(event: QEvent) -> None:
    """A claimed ShortcutOverride stays accepted, so the shell key does not fire."""
    override = getattr(getattr(QEvent, "Type", QEvent), "ShortcutOverride")
    if event.type() != override:
        return
    event.accept()


def _focus_policy() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "StrongFocus")


def _no_focus() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "NoFocus")


def _transparent() -> Qt.WidgetAttribute:
    attrs = getattr(Qt, "WidgetAttribute", Qt)
    return getattr(attrs, "WA_TransparentForMouseEvents")


class FormCanvas(QGraphicsView):
    """Dot grid, centred page, and the chrome around it."""

    def __init__(
        self,
        session: FormSession,
        realizer: Realizer,
        host: CanvasHost,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._realizer = realizer
        self._tokens: Optional[ShellThemeTokens] = None
        self._palette = _palette(None)
        self._canvas_bg = self._palette.backdrop.fill
        self._dot = self._palette.backdrop.dot
        self.setObjectName("formBuilder.canvas")
        self.setAccessibleName("Form canvas")
        self.setFocusPolicy(_focus_policy())
        # Qt focuses the viewport, not the view.
        self.viewport().setAccessibleName("Form canvas")
        shape = getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")
        self.setFrameShape(shape)
        drag = getattr(QGraphicsView, "DragMode", QGraphicsView)
        self.setDragMode(getattr(drag, "NoDrag"))
        self.setInteractive(False)
        scene = QGraphicsScene(self)
        isolate_scene(scene)
        self.setScene(scene)
        self.viewport().setMouseTracking(True)
        self._index = HitIndex(LiveGeometrySource(realizer))
        self._hit_sub = session.log.subscribe(
            HitIndexInvalidator(self._index).on_changeset, priority=PRIORITY_HIT_INDEX
        )
        self._stage = Stage(self, session, realizer, self._index.invalidate)
        self._stage.set_banner_push(PAGE_TITLE_HEIGHT)
        self._build_chrome()
        self._controller = CanvasController(self, session, realizer, self._index, self._stage, host)
        # Same priority as the controller's view listener, subscribed after it,
        # so the caption follows the page the controller just placed.
        self._chrome_sub = session.log.subscribe(self._position_after, priority=PRIORITY_VIEWS)
        realizer.build()
        self._chip_viewport = visible_scene_rect(self)
        self.horizontalScrollBar().valueChanged.connect(self._position_chrome)
        self.verticalScrollBar().valueChanged.connect(self._position_chrome)
        self.horizontalScrollBar().sliderReleased.connect(self._refresh_chips_after_scroll)
        self.verticalScrollBar().sliderReleased.connect(self._refresh_chips_after_scroll)
        # Track clicks, arrow buttons and keys move the bars without a release.
        # One 0 ms timer folds both bars' changes into one re-solve.
        self._chip_timer = QTimer(self)
        self._chip_timer.setSingleShot(True)
        self._chip_timer.setInterval(0)
        self._chip_timer.timeout.connect(self._refresh_chips_after_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._scroll_moved)
        self.verticalScrollBar().valueChanged.connect(self._scroll_moved)
        self._stage.place()
        self._sync_title()
        self._position_chrome()

    def page_widget(self) -> Optional[QWidget]:
        root = self._realizer.root_widget
        if root is None or not wrapper_is_valid(root):
            return None
        return root

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Chrome only. The page palette stays the runtime palette."""
        self._tokens = tokens
        self._palette = _palette(tokens)
        self._canvas_bg = self._palette.backdrop.fill
        self._dot = self._palette.backdrop.dot
        self.setProperty("formBuilderHighContrast", tokens.is_high_contrast)
        self.viewport().setProperty("formBuilderHighContrast", tokens.is_high_contrast)
        self._apply_page_chrome(tokens)
        width = tokens.focus_border_width
        self.setStyleSheet(
            "QGraphicsView#formBuilder\\.canvas {"
            f" background: {self._canvas_bg}; border: 1px solid {tokens.border}; }}"
            "QGraphicsView#formBuilder\\.canvas:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
            "QLabel#formBuilder\\.name {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 1px 6px;"
            " font-size: 11px; font-weight: 600; }"
            "QLabel#formBuilder\\.sizeReadout {"
            f" color: {tokens.text_muted}; background: transparent; border: none; padding: 0; }}"
            "QLabel#formBuilder\\.toast {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; padding: 4px 8px; }}"
        )
        self._stage.apply_palette(self._palette.backdrop)
        fill = tokens.tree_selected_bg
        text = on_accent_for(fill)
        self._stage.set_page_chip_selected_style(
            "QLabel { color: %s; background: %s; border: 1px solid %s;"
            " border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 600; }"
            % (text, fill, fill)
        )
        self.viewport().update()
        self._position_chrome()

    def send(self, event: HostEvent) -> None:
        self._controller.post(event)

    def focus_view(self) -> None:
        self.setFocus()

    def geometry_entries(self) -> Tuple[GeoEntry, ...]:
        return self._controller.geometry_entries()

    def edit_for_join(self, node: NodeId, token: str) -> None:
        self._controller.edit_for_join(node, token)

    def set_drag_look(self, paint: Optional[DropPaint]) -> None:
        self._stage.set_drag_look(paint)
        self._controller.set_drop_paint(paint)

    def show_page(self, container: NodeId, index: int) -> None:
        self._stage.show_page(container, index)

    def page_controls(self) -> Tuple[PageControl, ...]:
        return self._controller.frame.controls

    def slot_open(self) -> bool:
        return self._controller.slot_open()

    def end_slot(self) -> None:
        self._controller.end_slot()

    def pointer_global(self) -> Point:
        return self._controller.pointer_global()

    def form_point(self, global_pos: QPoint) -> Point:
        port = self.viewport().mapFromGlobal(global_pos)
        scene = self.mapToScene(port)
        form = self._stage.view_map().to_form(CanvasPoint(int(scene.x()), int(scene.y())))
        return Point(int(form.x), int(form.y))

    def overlay(self) -> OverlayFrame:
        return self._controller.frame

    def visible_canvas_rect(self) -> CanvasRect:
        return visible_scene_rect(self)

    def ensure_widget_visible(self, object_name: str) -> None:
        """Scroll so the named widget on the page is inside the viewport."""
        root = self.page_widget()
        if root is None or not object_name:
            return
        target = root if root.objectName() == object_name else root.findChild(QWidget, object_name)
        if target is None or not wrapper_is_valid(target):
            return
        origin = target.mapTo(root, QPoint(0, 0))
        rect = QRectF(
            float(origin.x()),
            float(origin.y()),
            float(max(target.width(), 1)),
            float(max(target.height(), 1)),
        )
        scene = self._stage.proxy.mapRectToScene(rect)
        left = int(scene.left())
        top = int(scene.top())
        self._stage.reveal_canvas(
            CanvasRect(left, top, max(1, int(scene.right()) - left), max(1, int(scene.bottom()) - top))
        )

    def refresh_chip(self) -> None:
        self._sync_title()
        self._stage.refresh_chrome()
        self._position_chrome()

    def detach(self) -> None:
        self._stage.detach()

    def dispose(self) -> None:
        self._controller.dispose()
        self._chrome_sub.close()
        self._hit_sub.close()
        self.detach()

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802
        controller = getattr(self, "_controller", None)
        if controller is None:
            return bool(super().viewportEvent(event))
        if controller.handle(event):
            _keep_claimed_shortcut(event)
            return True
        return bool(super().viewportEvent(event))

    def event(self, event: QEvent) -> bool:  # noqa: N802
        # Qt sends events from inside the QWidget constructor, before the
        # controller exists.
        controller = getattr(self, "_controller", None)
        if controller is None:
            return bool(super().event(event))
        if controller.handle(event):
            _keep_claimed_shortcut(event)
            return True
        return bool(super().event(event))

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: N802
        del next
        return False

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._position_chrome()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        controller = getattr(self, "_controller", None)
        if controller is None:
            return
        frame = controller.frame
        paint_frame(painter, frame, self._palette, rect)
        self._title.set_docked(_docked(frame), self._palette)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor(self._canvas_bg))
        if not self._dot:
            return
        color = QColor(self._dot)
        pen = getattr(getattr(Qt, "PenStyle", Qt), "NoPen")
        painter.setPen(pen)
        painter.setBrush(color)
        left = int(rect.left()) - (int(rect.left()) % _DOT)
        top = int(rect.top()) - (int(rect.top()) % _DOT)
        right = int(rect.right()) + _DOT
        bottom = int(rect.bottom()) + _DOT
        y = top
        while y < bottom:
            x = left
            while x < right:
                painter.drawEllipse(x, y, 2, 2)
                x += _DOT
            y += _DOT

    def _build_chrome(self) -> None:
        self._toast = QLabel(self)
        self._toast.setObjectName("formBuilder.toast")
        self._toast.setAccessibleName("Notice")
        self._toast.hide()
        self._title = _PageTitle(self)
        self._frame = QWidget(self)
        self._frame.setObjectName("formBuilder.pageFrame")
        self._frame.setFocusPolicy(_no_focus())
        self._frame.setAttribute(_transparent(), True)
        self._stage.track_chrome(self._title)
        self._stage.dock_on(self._title)

    def _sync_title(self) -> None:
        self._title.setText(page_title_text(self._session.document))

    def _position_after(self, _changeset: object) -> None:
        self._sync_title()
        self._position_chrome()

    def _scroll_moved(self, _value: int) -> None:
        # A drag re-solves once on sliderReleased.
        if self.horizontalScrollBar().isSliderDown() or self.verticalScrollBar().isSliderDown():
            return
        self._chip_timer.start()

    def _refresh_chips_after_scroll(self) -> None:
        rect = visible_scene_rect(self)
        if rect == self._chip_viewport:
            return
        self._chip_viewport = rect
        controller = getattr(self, "_controller", None)
        if controller is not None:
            controller.refresh_overlay()

    def _position_chrome(self) -> None:
        proxy = self._stage.proxy
        if proxy.widget() is None:
            return
        self._stage.position_labels()
        rect = proxy.sceneBoundingRect()
        top_left = self.mapFromScene(rect.topLeft())
        bottom_right = self.mapFromScene(rect.bottomRight())
        page_width = max(1, bottom_right.x() - top_left.x())
        page_height = max(1, bottom_right.y() - top_left.y())
        title_y = max(0, top_left.y() - PAGE_TITLE_HEIGHT)
        self._title.setFixedWidth(page_width)
        self._title.move(top_left.x(), title_y)
        self._title.raise_()
        self._frame.setGeometry(top_left.x(), title_y, page_width, page_height + PAGE_TITLE_HEIGHT)
        self._frame.lower()
        self._place_toast()

    def _apply_page_chrome(self, tokens: ShellThemeTokens) -> None:
        shadow = page_shadow_rgba(is_dark=tokens.is_dark, is_high_contrast=tokens.is_high_contrast)
        proxy = self._stage.proxy
        if shadow is None:
            proxy.setGraphicsEffect(None)
        else:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(18)
            effect.setOffset(0, 2)
            effect.setColor(QColor(*shadow))
            proxy.setGraphicsEffect(effect)
        _apply_page_chrome_style(self._title, self._frame, tokens)

    def _place_toast(self) -> None:
        if self._toast.isVisible():
            self._toast.adjustSize()
            toast_x = max(0, (self.width() - self._toast.width()) // 2)
            self._toast.move(toast_x, self.height() - self._toast.height() - 16)


def _palette(tokens: Optional[ShellThemeTokens]) -> CanvasPalette:
    if tokens is None:
        fill, dot = backdrop_colors(is_dark=False, is_high_contrast=False)
        return CanvasPalette(
            overlay=overlay_palette(False),
            backdrop=BackdropPalette(
                fill=fill,
                dot=dot,
                faint="#666F76",
                accent="#3366FF",
                muted="#5A6168",
                panel="#FFFFFF",
                border="#DEE2E6",
                text="#212529",
            ),
        )
    fill, dot = backdrop_colors(is_dark=tokens.is_dark, is_high_contrast=tokens.is_high_contrast)
    return CanvasPalette(
        overlay=overlay_palette(tokens.is_high_contrast),
        backdrop=BackdropPalette(
            fill=fill,
            dot=dot,
            faint=tokens.gutter_text or tokens.text_muted,
            accent=tokens.accent,
            muted=tokens.text_muted,
            panel=tokens.panel_bg,
            border=tokens.border,
            text=tokens.text_primary,
        ),
    )


def _apply_page_chrome_style(title: QWidget, frame: QWidget, tokens: Optional[ShellThemeTokens]) -> None:
    border = ""
    if tokens is not None and tokens.is_high_contrast:
        border = tokens.text_primary
    setter = getattr(title, "set_border", None)
    if callable(setter):
        setter(border)
    frame_border = "1px solid %s" % border if border else "none"
    frame.setStyleSheet(
        "QWidget#formBuilder\\.pageFrame { background: transparent; border: %s; }" % frame_border
    )


def _docked(frame: OverlayFrame) -> Tuple[Tuple[Chip, int, int], ...]:
    """Docked chips with the dock origin they were solved against."""
    dock = frame.dock
    if dock is None:
        return ()
    return tuple(
        (item, dock.x, dock.y) for item in frame.items if isinstance(item, Chip) and item.docked
    )


def _title_font() -> QFont:
    font = QFont(startup_font())
    font.setPixelSize(11)
    weight = getattr(getattr(QFont, "Weight", QFont), "DemiBold")
    font.setWeight(weight)
    return font


class _PageTitle(QWidget):
    """22 px caption. Fill, glyphs, and title text stay the same in every theme."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.pageTitle")
        self.setAccessibleName("Page title")
        self.setFixedHeight(PAGE_TITLE_HEIGHT)
        self.setFont(_title_font())
        self._text = ""
        self._border = ""
        self._docked: Tuple[Tuple[Chip, int, int], ...] = ()
        self._palette: Optional[CanvasPalette] = None

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt-style setter the canvas already calls
        self._text = text
        self.update()

    def set_border(self, color: str) -> None:
        self._border = color
        self.update()

    def set_docked(self, docked: Tuple[Tuple[Chip, int, int], ...], palette: CanvasPalette) -> None:
        """Selection chips that had no clear seat on the canvas sit on this strip."""
        if docked == self._docked and palette is self._palette:
            return
        self._docked = docked
        self._palette = palette
        self.update()

    def docked(self) -> Tuple[Chip, ...]:
        return tuple(item for item, _x, _y in self._docked)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PAGE_TITLE_FILL))
        if self._border:
            pen = QPen(QColor(self._border))
            painter.setPen(pen)
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.setFont(self.font())
        painter.setPen(QColor(PAGE_TITLE_TEXT))
        metrics = painter.fontMetrics()
        available = max(0, self.width() - 8 - 56)
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
        shown = metrics.elidedText(self._text, elide, available)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        painter.drawText(8, baseline, shown)
        _paint_caption_glyphs(painter, self.width())
        if self._palette is not None:
            for item, dock_x, dock_y in self._docked:
                painter.save()
                painter.translate(-dock_x, -dock_y)
                paint_docked_chip(painter, item, self._palette)
                painter.restore()
        painter.end()


def _paint_caption_glyphs(painter: QPainter, width: int) -> None:
    pen = QPen(QColor(PAGE_TITLE_GLYPH))
    pen.setWidth(1)
    painter.setPen(pen)
    no_brush = getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush")
    painter.setBrush(no_brush)
    size = 10
    top = 6
    right = width - 8
    close_x = right - size
    painter.drawLine(close_x, top, close_x + size, top + size)
    painter.drawLine(close_x, top + size, close_x + size, top)
    square_x = close_x - size - 6
    painter.drawRect(square_x, top, size, size)
    dash_x = square_x - size - 6
    mid = top + size // 2
    painter.drawLine(dash_x, mid, dash_x + size, mid)


__all__ = ["FormCanvas"]
