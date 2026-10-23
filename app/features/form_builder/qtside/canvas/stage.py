"""The page on the backdrop. The single owner of the page rect.

Root geometry in the document wins. This stage does not replace it with the
layout's size hint. Without that property the page is the hint grown to the
minimum, and that size is not saved.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QGraphicsProxyWidget, QGraphicsView, QLabel, QWidget
from app.qt.qt_compat import wrapper_is_valid

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import InvalidationReason, Rect
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.gesture import (
    Cursor,
    EndPreview,
    Preview,
    PreviewPage,
    Reveal,
    ScrollBy,
    Tip,
    ViewEffect,
    Zoom,
)
from app.features.form_builder.qtside.canvas.core.space import (
    GUTTERS,
    CanvasPoint,
    CanvasRect,
    CanvasSize,
    Fit,
    Size,
    ViewMap,
    ZoomSetting,
    anchored_scroll,
    apply_zoom,
    layout_page,
    page_request,
    zoom_factor,
)
from app.features.form_builder.qtside.canvas.core.words import page_chip_label
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import BackdropPalette

_REVEAL_PAD = 16
_CURSORS = {
    "arrow": "ArrowCursor",
    "move": "SizeAllCursor",
    "forbidden": "ForbiddenCursor",
    "pointing": "PointingHandCursor",
    "size_h": "SizeHorCursor",
    "size_v": "SizeVerCursor",
    "size_fdiag": "SizeFDiagCursor",
    "size_bdiag": "SizeBDiagCursor",
    "open_hand": "OpenHandCursor",
    "closed_hand": "ClosedHandCursor",
}


def _no_focus() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "NoFocus")


def _transparent() -> Qt.WidgetAttribute:
    attrs = getattr(Qt, "WidgetAttribute", Qt)
    return getattr(attrs, "WA_TransparentForMouseEvents")


class Stage:
    def __init__(
        self,
        view: QGraphicsView,
        session: FormSession,
        realizer: Realizer,
        invalidate: Callable[[InvalidationReason], None],
    ) -> None:
        self._view = view
        self._session = session
        self._realizer = realizer
        self._invalidate = invalidate
        self._zoom: ZoomSetting = Fit()
        self._factor = 0.0
        self._banner_push = 0
        self._preview_ids: Tuple[NodeId, ...] = ()
        self._page_preview = False
        self._form_selected = False
        self._backdrop: Optional[BackdropPalette] = None
        self._proxy = QGraphicsProxyWidget()
        scene = view.scene()
        if scene is None:
            raise RuntimeError("canvas stage requires a scene")
        scene.addItem(self._proxy)
        self._name = _label(view, "formBuilder.name", "Form name")
        self._size = _label(view, "formBuilder.sizeReadout", "Page size")

    @property
    def proxy(self) -> QGraphicsProxyWidget:
        return self._proxy

    def place(self) -> None:
        """Attach the root, keep a positive document size, and lay out the page."""
        root = self._attach()
        if root is None:
            return
        if self._settle_root_size(root):
            self._invalidate("root_resize")
        if not self._page_preview:
            factor = zoom_factor(self._zoom, Size(root.width(), root.height()), _viewport(self._view))
            if factor != self._factor:
                self._invalidate("zoom")
                self._factor = factor
        self._proxy.setScale(self._factor or 1.0)
        if self._page_preview:
            self._grow_scene(root)
        else:
            placed = layout_page(
                Size(root.width(), root.height()),
                self._factor or 1.0,
                _viewport(self._view),
                self._banner_push,
            )
            self._proxy.setPos(placed.page_origin.x, placed.page_origin.y)
            scene = self._view.scene()
            scene.setSceneRect(0, 0, placed.scene.width, placed.scene.height)
        self._refresh_labels(root)
        self.position_labels()

    def detach(self) -> None:
        widget = self._proxy.widget()
        if widget is not None:
            self._proxy.setWidget(None)

    def view_map(self) -> ViewMap:
        root = self._realizer.root_widget
        if root is None:
            page = Size(1, 1)
        else:
            page = Size(max(root.width(), 1), max(root.height(), 1))
        origin = self._proxy.pos()
        return ViewMap(self._factor or 1.0, CanvasPoint(int(origin.x()), int(origin.y())), page)

    def page_minimum(self) -> Size:
        root = self._realizer.root_widget
        if root is None:
            return Size(1, 1)
        minimum = root.minimumSize()
        return Size(max(minimum.width(), 1), max(minimum.height(), 1))

    def chrome_rects(self) -> Tuple[CanvasRect, ...]:
        scroll_x = self._view.horizontalScrollBar().value()
        scroll_y = self._view.verticalScrollBar().value()
        rects = []
        for label in (self._name, self._size):
            if label.isHidden():
                continue
            rects.append(
                CanvasRect(label.x() + scroll_x, label.y() + scroll_y, label.width(), label.height())
            )
        return tuple(rects)

    def set_form_selected(self, selected: bool) -> None:
        self._form_selected = selected

    def apply_palette(self, backdrop: BackdropPalette) -> None:
        self._backdrop = backdrop

    def position_labels(self) -> None:
        if self._proxy.widget() is None:
            return
        rect = self._proxy.sceneBoundingRect()
        top_left = self._view.mapFromScene(rect.topLeft())
        bottom_right = self._view.mapFromScene(rect.bottomRight())
        _fit_label(self._name)
        _fit_label(self._size)
        self._name.move(top_left.x(), max(0, top_left.y() - self._name.height() - 4))
        self._name.raise_()
        size_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - self._size.width()) // 2)
        self._size.move(size_x, bottom_right.y() + 6)
        self._size.raise_()

    def run(self, effect: ViewEffect) -> None:
        if isinstance(effect, Zoom):
            self._run_zoom(effect)
        elif isinstance(effect, Preview):
            self._run_preview(effect)
        elif isinstance(effect, PreviewPage):
            self._run_preview_page(effect)
        elif isinstance(effect, EndPreview):
            self._run_end_preview()
        elif isinstance(effect, ScrollBy):
            horizontal = self._view.horizontalScrollBar()
            vertical = self._view.verticalScrollBar()
            horizontal.setValue(horizontal.value() + effect.dx)
            vertical.setValue(vertical.value() + effect.dy)
        elif isinstance(effect, Reveal):
            self._reveal(effect.rect)
        elif isinstance(effect, Cursor):
            self._view.viewport().setCursor(getattr(Qt, _CURSORS[effect.shape]))
        elif isinstance(effect, Tip):
            self._view.viewport().setToolTip(effect.text)

    def _attach(self) -> Optional[QWidget]:
        root = self._realizer.root_widget
        if root is None:
            return None
        current = self._proxy.widget()
        if current is not root:
            if current is not None and wrapper_is_valid(current):
                self._proxy.setWidget(None)
            self._proxy.setWidget(root)
        return root

    def _settle_root_size(self, root: QWidget) -> bool:
        if self._page_preview:
            return False
        width = root.width()
        height = root.height()
        entry = self._session.document.root.prop("geometry")
        value = entry.value if entry is not None else None
        if isinstance(value, RectValue) and value.width > 0 and value.height > 0:
            if width == value.width and height == value.height:
                return False
            root.resize(value.width, value.height)
            return True
        hint = root.sizeHint()
        minimum = root.minimumSize()
        requested = page_request(
            None,
            Size(max(hint.width(), 1), max(hint.height(), 1)),
            Size(max(minimum.width(), 1), max(minimum.height(), 1)),
        )
        if requested is None or (width == requested.width and height == requested.height):
            return False
        root.resize(requested.width, requested.height)
        return True

    def _grow_scene(self, root: QWidget) -> None:
        factor = self._factor or 1.0
        width = max(1, int(round(root.width() * factor)))
        height = max(1, int(round(root.height() * factor)))
        origin = self._proxy.pos()
        viewport = _viewport(self._view)
        scene_w = max(viewport.width, int(origin.x()) + width + GUTTERS.right)
        scene_h = max(viewport.height, int(origin.y()) + height + GUTTERS.bottom)
        self._view.scene().setSceneRect(0, 0, scene_w, scene_h)

    def _refresh_labels(self, root: QWidget) -> None:
        label = page_chip_label(self._session.document, "Form")
        self._name.setText(label)
        self._name.setAccessibleName(label)
        self._size.setText("%d × %d" % (root.width(), root.height()))

    def _run_zoom(self, effect: Zoom) -> None:
        before = self.view_map()
        self._zoom = apply_zoom(self._zoom, effect.change, self._factor or 1.0)
        self.place()
        if effect.anchor is None:
            return
        scroll = CanvasPoint(
            self._view.horizontalScrollBar().value(),
            self._view.verticalScrollBar().value(),
        )
        nxt = anchored_scroll(before, self.view_map(), CanvasPoint(effect.anchor.x, effect.anchor.y), scroll)
        self._view.horizontalScrollBar().setValue(nxt.x)
        self._view.verticalScrollBar().setValue(nxt.y)

    def _run_preview(self, effect: Preview) -> None:
        self._preview_ids = tuple(node for node, _rect in effect.rects)
        self._page_preview = False
        for node, rect in effect.rects:
            widget = self._realizer.widget_for(node)
            if widget is None:
                continue
            widget.setGeometry(rect.x, rect.y, rect.width, rect.height)

    def _run_preview_page(self, effect: PreviewPage) -> None:
        root = self._realizer.root_widget
        if root is None:
            return
        self._page_preview = True
        self._preview_ids = (self._session.document.root.id,)
        root.resize(effect.size.width, effect.size.height)
        self._proxy.setScale(self._factor or 1.0)
        self._grow_scene(root)
        self._refresh_labels(root)
        self.position_labels()

    def _run_end_preview(self) -> None:
        ids = self._preview_ids
        self._preview_ids = ()
        self._page_preview = False
        if ids:
            self._realizer.reapply_geometry(ids)
        self.place()
        # The frozen index is stale even when the root size came back unchanged.
        self._invalidate("root_resize")

    def _reveal(self, rect: Rect) -> None:
        canvas = self.view_map().to_canvas(rect).grown(_REVEAL_PAD)
        horizontal = self._view.horizontalScrollBar()
        vertical = self._view.verticalScrollBar()
        left = horizontal.value()
        top = vertical.value()
        right = left + self._view.viewport().width()
        bottom = top + self._view.viewport().height()
        dx = 0
        dy = 0
        if canvas.x < left:
            dx = canvas.x - left
        elif canvas.x + canvas.width > right:
            dx = canvas.x + canvas.width - right
        if canvas.y < top:
            dy = canvas.y - top
        elif canvas.y + canvas.height > bottom:
            dy = canvas.y + canvas.height - bottom
        horizontal.setValue(left + dx)
        vertical.setValue(top + dy)


def _viewport(view: QGraphicsView) -> CanvasSize:
    viewport = view.viewport()
    return CanvasSize(max(viewport.width(), 1), max(viewport.height(), 1))


def _label(parent: QGraphicsView, name: str, accessible: str) -> QLabel:
    label = QLabel(parent)
    label.setObjectName(name)
    label.setAccessibleName(accessible)
    label.setFocusPolicy(_no_focus())
    label.setAttribute(_transparent(), True)
    return label


def _fit_label(label: QLabel) -> None:
    text = label.text()
    width = label.fontMetrics().horizontalAdvance(text) + 16
    height = max(22, label.fontMetrics().height() + 8)
    label.setFixedSize(max(width, 8), height)
