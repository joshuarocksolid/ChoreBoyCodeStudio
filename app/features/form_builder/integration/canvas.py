"""Design canvas (UX-WB-004).

The realized form sits in a proxy on the runtime scene. Chip, size, grabbers
and the toast are chrome on the view, so a theme change does not restyle the
page. Nothing on the canvas selects or drags in this slice.
"""

from __future__ import annotations

from typing import Callable, Optional

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

from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX, PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.canvas.stage import Stage
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import backdrop_fill
from app.features.form_builder.qtside.theme.runtime import isolate_scene
from app.shell.theme_tokens import ShellThemeTokens

_DETACH_BEFORE_REALIZE = 9
_DOT = 16


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

    def __init__(self, session: FormSession, realizer: Realizer, parent: QWidget) -> None:
        super().__init__(parent)
        self._session = session
        self._realizer = realizer
        self._tokens: Optional[ShellThemeTokens] = None
        self._canvas_bg = "#E9EBEF"
        self._dot = "#D3D8DF"
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
        self._index = HitIndex(LiveGeometrySource(realizer))
        self._hit_sub = session.log.subscribe(
            HitIndexInvalidator(self._index).on_changeset, priority=PRIORITY_HIT_INDEX
        )
        self._stage = Stage(self, session, realizer, self._index.invalidate)
        # setWidget(None) drops the proxy's hold without deleting the widget.
        # The realizer deletes the old root on a replace. Detach first.
        self._detach_sub = session.log.subscribe(self._detach_for_replace, priority=_DETACH_BEFORE_REALIZE)
        self._view_sub = session.log.subscribe(self._sync_root, priority=PRIORITY_VIEWS)
        realizer.build()
        self._build_chrome()
        self.viewport().installEventFilter(self)
        self.horizontalScrollBar().valueChanged.connect(self._position_chrome)
        self.verticalScrollBar().valueChanged.connect(self._position_chrome)
        self._stage.place()
        self._position_chrome()

    def page_widget(self) -> Optional[QWidget]:
        root = self._realizer.root_widget
        if root is None or not wrapper_is_valid(root):
            return None
        return root

    def set_drawer_closer(self, callback: Callable[[], None]) -> None:
        self._closer = callback

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Chrome only. The page palette stays the runtime palette."""
        self._tokens = tokens
        self._canvas_bg, self._dot = _backdrop(tokens)
        width = tokens.focus_border_width
        faint = tokens.gutter_text or tokens.text_muted
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
            "QWidget#formBuilder\\.grabberRight, QWidget#formBuilder\\.grabberBottom {"
            f" background: {faint}; border: none; }}"
            "QLabel#formBuilder\\.toast {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; padding: 4px 8px; }}"
        )
        self.viewport().update()
        self._position_chrome()

    def refresh_chip(self) -> None:
        self._stage.place()
        self._position_chrome()

    def detach(self) -> None:
        self._stage.detach()

    def dispose(self) -> None:
        self._detach_sub.close()
        self._view_sub.close()
        self._hit_sub.close()
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
        self._stage.place()
        self._position_chrome()

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
        self._stage.place()
        self._position_chrome()

    def _position_chrome(self) -> None:
        proxy = self._stage.proxy
        if proxy.widget() is None:
            return
        self._stage.position_labels()
        rect = proxy.sceneBoundingRect()
        top_left = self.mapFromScene(rect.topLeft())
        bottom_right = self.mapFromScene(rect.bottomRight())
        mid_y = top_left.y() + max(0, (bottom_right.y() - top_left.y() - 32) // 2)
        self._grabber_right.move(bottom_right.x() + 2, mid_y)
        self._grabber_right.raise_()
        mid_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - 32) // 2)
        self._grabber_bottom.move(mid_x, bottom_right.y() + 2)
        self._grabber_bottom.raise_()
        self._place_toast()

    def _place_toast(self) -> None:
        if self._toast.isVisible():
            self._toast.adjustSize()
            toast_x = max(0, (self.width() - self._toast.width()) // 2)
            self._toast.move(toast_x, self.height() - self._toast.height() - 16)


def _backdrop(tokens: ShellThemeTokens) -> tuple[str, str]:
    return backdrop_fill(tokens.is_dark, tokens.is_high_contrast)


__all__ = ["FormCanvas"]
