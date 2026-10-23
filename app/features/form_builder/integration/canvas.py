"""Design canvas (UX-WB-004).

The realized form sits in a proxy on the runtime scene. The controller owns
selection, hover and gestures. ``drawForeground`` paints the overlay frame.
The toast stays view chrome.
"""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import QEvent, QRectF, Qt
from app.qt.QtGui import QColor, QPainter
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid

from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX, PRIORITY_VIEWS
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.canvas.controller import CanvasController, CanvasHost
from app.features.form_builder.qtside.canvas.core.frame import OverlayFrame
from app.features.form_builder.qtside.canvas.core.gesture import HostEvent
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.canvas.paint import paint_frame
from app.features.form_builder.qtside.canvas.stage import Stage
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import (
    BackdropPalette,
    CanvasPalette,
    backdrop_fill,
    overlay_palette,
)
from app.features.form_builder.qtside.theme.runtime import isolate_scene
from app.shell.theme_tokens import ShellThemeTokens

_DOT = 16


def _focus_policy() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "StrongFocus")


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
        self._build_chrome()
        self._controller = CanvasController(self, session, realizer, self._index, self._stage, host)
        # Same priority as the controller's view listener, subscribed after it,
        # so grabbers follow the page the controller just placed.
        self._chrome_sub = session.log.subscribe(self._position_after, priority=PRIORITY_VIEWS)
        realizer.build()
        self.horizontalScrollBar().valueChanged.connect(self._position_chrome)
        self.verticalScrollBar().valueChanged.connect(self._position_chrome)
        self._stage.place()
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
        self.viewport().update()
        self._position_chrome()

    def send(self, event: HostEvent) -> None:
        self._controller.post(event)

    def overlay(self) -> OverlayFrame:
        return self._controller.frame

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
        return bool(controller.handle(event) or super().viewportEvent(event))

    def event(self, event: QEvent) -> bool:  # noqa: N802
        # Qt sends events from inside the QWidget constructor, before the
        # controller exists.
        controller = getattr(self, "_controller", None)
        if controller is None:
            return bool(super().event(event))
        return bool(controller.handle(event) or super().event(event))

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
        paint_frame(painter, controller.frame, self._palette, rect)

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

    def _position_after(self, _changeset: object) -> None:
        self._position_chrome()

    def _position_chrome(self) -> None:
        proxy = self._stage.proxy
        if proxy.widget() is None:
            return
        self._stage.position_labels()
        self._place_toast()

    def _place_toast(self) -> None:
        if self._toast.isVisible():
            self._toast.adjustSize()
            toast_x = max(0, (self.width() - self._toast.width()) // 2)
            self._toast.move(toast_x, self.height() - self._toast.height() - 16)


def _palette(tokens: Optional[ShellThemeTokens]) -> CanvasPalette:
    if tokens is None:
        fill, dot = backdrop_fill(False, False)
        # Light shell colours until apply_theme runs. Overlay hues stay on the palette.
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
    fill, dot = backdrop_fill(tokens.is_dark, tokens.is_high_contrast)
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


__all__ = ["FormCanvas"]
