"""The page on the backdrop. The single owner of the page rect.

Root geometry in the document wins. This stage does not replace it with the
layout's size hint. Without that property the page is the hint grown to the
minimum, and that size is not saved.
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from app.qt.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from app.qt.QtWidgets import QGraphicsProxyWidget, QGraphicsView, QLabel, QWidget
from app.qt.qt_compat import delete_now, enum_value, wrapper_is_valid

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.preview_state import PreviewState
from app.features.form_builder.engine.query.hit_index import InvalidationReason, Rect
from app.features.form_builder.engine.query.selection import SelectionSource
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
    PagePlacement,
    Size,
    ViewMap,
    ZoomFit,
    ZoomSetting,
    anchored_scroll,
    apply_zoom,
    reveal_axis,
    layout_page,
    page_request,
    zoom_factor,
)
from app.features.form_builder.qtside.canvas.core.widths import WIDE_DEFAULT, arrange_widths
from app.features.form_builder.qtside.canvas.core.words import describe_selection, page_chip_label
from app.features.form_builder.qtside.canvas.preview_apply import apply_preview
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import BackdropPalette
from app.features.form_builder.qtside.theme.runtime import startup_font

# Same slot as the primary detach. build() deletes the root the proxy is holding.
_BEFORE_REALIZE = 9

# Handle hit, chip height, and the gap, in screen pixels. The page scale lives on the proxy.
REVEAL_PAD = 32
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
        self._preview = PreviewState()
        self._widths_on = False
        self._wide_px = WIDE_DEFAULT
        self._wide_realizer: Optional[Realizer] = None
        self._wide_proxy: Optional[QGraphicsProxyWidget] = None
        self._clicks: Optional[_CopyClicks] = None
        self._preview_ids: Tuple[NodeId, ...] = ()
        self._page_preview = False
        self._form_selected = False
        self._selected_page_style = ""
        self._backdrop: Optional[BackdropPalette] = None
        self._extra: Tuple[QWidget, ...] = ()
        self._dock: Optional[QWidget] = None
        self._proxy = QGraphicsProxyWidget()
        scene = view.scene()
        if scene is None:
            raise RuntimeError("canvas stage requires a scene")
        scene.addItem(self._proxy)
        self._name = _label(view, "formBuilder.name", "Form name")
        self._size = _label(view, "formBuilder.sizeReadout", "Page size")
        self._narrow_label = _label(view, "formBuilder.narrowLabel", "Narrowest")
        self._wide_label = _label(view, "formBuilder.wideLabel", "Wide")
        self._narrow_label.hide()
        self._wide_label.hide()
        self._detach_sub = session.log.subscribe(self._before_wide_realize, priority=_BEFORE_REALIZE)
        # The view follows the page's home scroll until the user or a reveal
        # scrolls it. Programmatic setValue does not emit actionTriggered.
        self._homed = True
        view.horizontalScrollBar().actionTriggered.connect(self._scrolled)
        view.verticalScrollBar().actionTriggered.connect(self._scrolled)

    @property
    def proxy(self) -> QGraphicsProxyWidget:
        return self._proxy

    @property
    def preview(self) -> PreviewState:
        return self._preview

    @property
    def widths_on(self) -> bool:
        return self._widths_on

    @property
    def wide_px(self) -> int:
        return self._wide_px

    @property
    def wide_realizer(self) -> Optional[Realizer]:
        return self._wide_realizer

    @property
    def wide_proxy(self) -> Optional[QGraphicsProxyWidget]:
        return self._wide_proxy

    def set_preview(self, state: PreviewState) -> None:
        self._preview = state

    def set_two_widths(self, on: bool) -> None:
        self._widths_on = on

    def set_wide_px(self, px: int) -> None:
        self._wide_px = max(1, px)

    def place(self) -> None:
        """Attach the root, keep a positive document size, and lay out the page."""
        root = self._attach()
        if root is None:
            return
        if self._widths_on:
            self._place_widths(root)
            return
        self.close_widths()
        apply_preview(root, self._preview, startup_font())
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
                0,
            )
            self._proxy.setPos(placed.page_origin.x, placed.page_origin.y)
            scene = self._view.scene()
            scene.setSceneRect(0, 0, placed.scene.width, placed.scene.height)
            if self._homed:
                self._go_home(placed)
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
        for widget in (self._name, self._size, self._narrow_label, self._wide_label, *self._extra):
            if widget.isHidden():
                continue
            rects.append(
                CanvasRect(widget.x() + scroll_x, widget.y() + scroll_y, widget.width(), widget.height())
            )
        return tuple(rects)

    def dock_rect(self) -> Optional[CanvasRect]:
        """The chrome strip a selection chip falls back to, in canvas pixels."""
        widget = self._dock
        if widget is None or widget.isHidden() or widget.width() <= 0:
            return None
        scroll_x = self._view.horizontalScrollBar().value()
        scroll_y = self._view.verticalScrollBar().value()
        return CanvasRect(widget.x() + scroll_x, widget.y() + scroll_y, widget.width(), widget.height())

    def dock_on(self, widget: QWidget) -> None:
        """A view widget that sticks to the top of the view: the page caption."""
        self._dock = widget

    def set_banner_push(self, pixels: int) -> None:
        """Lift the name chip above the caption. The page stays in the gutter."""
        self._banner_push = max(0, pixels)

    def track_chrome(self, *widgets: QWidget) -> None:
        """View widgets the chip solver must not cover. The stage does not move them."""
        self._extra = widgets

    def refresh_chrome(self) -> None:
        """Rewrite the page chip and size readout without moving the page."""
        root = self._realizer.root_widget
        if root is None or not wrapper_is_valid(root):
            return
        self._refresh_labels(root)
        self.position_labels()

    def set_form_selected(self, selected: bool) -> None:
        self._form_selected = selected
        self._apply_page_chip_style()

    def set_page_chip_selected_style(self, stylesheet: str) -> None:
        """Selection fill for the page name. Idle clears back to the view sheet."""
        self._selected_page_style = stylesheet
        self._apply_page_chip_style()

    def _apply_page_chip_style(self) -> None:
        # setStyleSheet sends a polish through the view. Repeating the same
        # sheet re-enters selection on some realized forms.
        if self._form_selected and self._selected_page_style:
            sheet = self._selected_page_style
        else:
            sheet = ""
        if self._name.styleSheet() == sheet:
            return
        self._name.setStyleSheet(sheet)

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
        lift = 0
        if self._widths_on:
            self._place_copy_label(self._narrow_label, self._proxy, above_title=True)
            self._place_copy_label(self._wide_label, self._wide_proxy, above_title=False)
            lift = self._narrow_label.height() + 4
        else:
            self._narrow_label.hide()
            self._wide_label.hide()
        self._name.move(
            top_left.x(),
            max(0, top_left.y() - self._banner_push - self._name.height() - 4 - lift),
        )
        self._name.raise_()
        size_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - self._size.width()) // 2)
        self._size.move(size_x, bottom_right.y() + 6)
        self._size.raise_()

    def sync_selection(self, text: str) -> None:
        """The wide copy reads the same selection sentence as the canvas."""
        realizer = self._wide_realizer
        if realizer is None:
            return
        root = realizer.root_widget
        if root is None:
            return
        root.setAccessibleDescription(text)

    def wide_canvas_rect(self, node_id: NodeId) -> Optional[CanvasRect]:
        """Where ``node_id`` sits on the wide copy, in canvas pixels."""
        realizer = self._wide_realizer
        proxy = self._wide_proxy
        if not self._widths_on or realizer is None or proxy is None:
            return None
        widget = realizer.widget_for(node_id)
        root = realizer.root_widget
        if widget is None or root is None:
            return None
        origin = widget.mapTo(root, QPoint(0, 0))
        local = QRectF(
            float(origin.x()),
            float(origin.y()),
            float(max(widget.width(), 1)),
            float(max(widget.height(), 1)),
        )
        scene = proxy.mapRectToScene(local)
        left = math.floor(scene.left())
        top = math.floor(scene.top())
        right = math.ceil(scene.right())
        bottom = math.ceil(scene.bottom())
        return CanvasRect(int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top)))

    def close(self) -> None:
        self._detach_sub.close()
        self.close_widths()

    def close_widths(self) -> None:
        """Drop the second copy. The primary keeps its registered resources."""
        self._widths_on = False
        self._release_wide_widget()
        realizer = self._wide_realizer
        proxy = self._wide_proxy
        self._wide_realizer = None
        self._wide_proxy = None
        if self._clicks is not None:
            self._clicks.clear()
            self._clicks = None
        if proxy is not None:
            scene = self._view.scene() if wrapper_is_valid(self._view) else None
            if scene is not None:
                scene.removeItem(proxy)
            delete_now(proxy)
        if realizer is not None:
            realizer.dispose()
        if wrapper_is_valid(self._narrow_label):
            self._narrow_label.hide()
        if wrapper_is_valid(self._wide_label):
            self._wide_label.hide()

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
            self._homed = False
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

    def _place_widths(self, root: QWidget) -> None:
        """Two live copies at one zoom. resize only. The file keeps its design size."""
        startup = startup_font()
        apply_preview(root, self._preview, startup)
        page = self._page_size_for_zoom(root)
        if not self._page_preview:
            factor = zoom_factor(self._zoom, page, _viewport(self._view))
            if factor != self._factor:
                self._invalidate("zoom")
                self._factor = factor
        wide_root = self._ensure_wide()
        proxy = self._wide_proxy
        if wide_root is None or proxy is None:
            return
        apply_preview(wide_root, self._preview, startup)
        _resize_live(root, max(root.minimumSizeHint().width(), 1), page.height)
        _resize_live(wide_root, self._wide_px, page.height)
        self._invalidate("root_resize")
        factor = self._factor or 1.0
        self._proxy.setScale(factor)
        proxy.setScale(factor)
        arranged = arrange_widths(
            Size(root.width(), root.height()),
            Size(wide_root.width(), wide_root.height()),
            factor,
            _viewport(self._view),
            self._banner_push,
        )
        self._proxy.setPos(arranged.narrow_at.x, arranged.narrow_at.y)
        proxy.setPos(arranged.wide_at.x, arranged.wide_at.y)
        self._view.scene().setSceneRect(0, 0, arranged.scene.width, arranged.scene.height)
        if self._homed:
            self._view.horizontalScrollBar().setValue(0)
            self._view.verticalScrollBar().setValue(0)
        self._narrow_label.setText("Narrowest \u00b7 %d px" % root.width())
        self._narrow_label.setAccessibleName(self._narrow_label.text())
        self._wide_label.setText("Wide \u00b7 %d px" % wide_root.width())
        self._wide_label.setAccessibleName(self._wide_label.text())
        self.sync_selection(describe_selection(self._session.document, self._session.selection.state))
        self._refresh_labels(root)
        self.position_labels()

    def _ensure_wide(self) -> Optional[QWidget]:
        if self._wide_realizer is None:
            # The primary realizer owns qrc registration. This copy must not unregister it.
            self._wide_realizer = Realizer(self._session, register_resources=False)
            self._wide_realizer.build()
            proxy = QGraphicsProxyWidget()
            self._view.scene().addItem(proxy)
            self._wide_proxy = proxy
            self._clicks = _CopyClicks(self._session, self._wide_realizer)
        realizer = self._wide_realizer
        proxy = self._wide_proxy
        if realizer is None or proxy is None:
            return None
        root = realizer.root_widget
        if root is None:
            return None
        current = proxy.widget()
        if current is not root:
            if current is not None and wrapper_is_valid(current):
                proxy.setWidget(None)
            proxy.setWidget(root)
        if self._clicks is not None:
            self._clicks.arm(root)
        return root

    def _page_size_for_zoom(self, root: QWidget) -> Size:
        """The design page, read before either copy is narrowed."""
        entry = self._session.document.root.prop("geometry")
        value = entry.value if entry is not None else None
        if isinstance(value, RectValue) and value.width > 0 and value.height > 0:
            return Size(value.width, value.height)
        hint = root.sizeHint()
        minimum = root.minimumSize()
        hint_w = hint.width() if hint.width() > 0 else max(root.width(), 320)
        hint_h = hint.height() if hint.height() > 0 else max(root.height(), 240)
        requested = page_request(
            None,
            Size(hint_w, hint_h),
            Size(max(minimum.width(), 1), max(minimum.height(), 1)),
        )
        if requested is None:
            return Size(max(root.width(), 1), max(root.height(), 1))
        return requested

    def _place_copy_label(
        self, label: QLabel, proxy: Optional[QGraphicsProxyWidget], *, above_title: bool
    ) -> None:
        if proxy is None or proxy.widget() is None:
            label.hide()
            return
        rect = proxy.sceneBoundingRect()
        top_left = self._view.mapFromScene(rect.topLeft())
        _fit_label(label)
        gap = self._banner_push if above_title else 0
        label.move(top_left.x(), max(0, top_left.y() - gap - label.height() - 4))
        label.show()
        label.raise_()

    def _before_wide_realize(self, changeset: object) -> None:
        if not getattr(changeset, "replaced", False):
            return
        if not wrapper_is_valid(self._view):
            return
        self._release_wide_widget()

    def _release_wide_widget(self) -> None:
        proxy = self._wide_proxy
        if proxy is None or not wrapper_is_valid(proxy):
            return
        if proxy.widget() is not None:
            proxy.setWidget(None)

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
        # No positive hint still leaves a page the caption can span.
        hint_w = hint.width() if hint.width() > 0 else max(width, 320)
        hint_h = hint.height() if hint.height() > 0 else max(height, 240)
        requested = page_request(
            None,
            Size(hint_w, hint_h),
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

    def _scrolled(self, _action: int) -> None:
        self._homed = False

    def _go_home(self, placed: PagePlacement) -> None:
        # centerOn, not setValue: a resize re-centres the view on its last
        # centre point, which setValue does not move.
        viewport = _viewport(self._view)
        self._view.centerOn(
            placed.home.x + viewport.width / 2.0,
            placed.home.y + viewport.height / 2.0,
        )

    def _run_zoom(self, effect: Zoom) -> None:
        before = self.view_map()
        self._zoom = apply_zoom(self._zoom, effect.change, self._factor or 1.0)
        if isinstance(effect.change, ZoomFit):
            self._homed = True
        self.place()
        if effect.anchor is None or isinstance(effect.change, ZoomFit):
            return
        self._homed = False
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
        self.reveal_canvas(self.view_map().to_canvas(rect))

    def reveal_canvas(self, canvas: CanvasRect) -> None:
        """Scroll only when ``canvas`` is not already in view (UX-SEL-009)."""
        horizontal = self._view.horizontalScrollBar()
        vertical = self._view.verticalScrollBar()
        port = _viewport(self._view)
        left = horizontal.value()
        top = vertical.value()
        x = reveal_axis(canvas.x, canvas.width, left, port.width, REVEAL_PAD)
        # The page caption pins over the top of the view once the page scrolls up.
        y = reveal_axis(canvas.y, canvas.height, top, port.height, REVEAL_PAD, self._banner_push)
        if x == left and y == top:
            return
        self._homed = False
        horizontal.setValue(x)
        vertical.setValue(y)


def _viewport(view: QGraphicsView) -> CanvasSize:
    viewport = view.viewport()
    return CanvasSize(max(viewport.width(), 1), max(viewport.height(), 1))


def visible_scene_rect(view: QGraphicsView) -> CanvasRect:
    """Scene rectangle currently inside the view, in canvas pixels."""
    mapped = view.mapToScene(view.viewport().rect()).boundingRect()
    left = math.floor(mapped.left())
    top = math.floor(mapped.top())
    right = math.ceil(mapped.right())
    bottom = math.ceil(mapped.bottom())
    return CanvasRect(left, top, max(1, right - left), max(1, bottom - top))


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


def _resize_live(widget: QWidget, width: int, height: int) -> None:
    """Preview size on the live widget. This is not a geometry command."""
    widget.resize(max(width, 1), max(height, 1))
    layout = widget.layout()
    if layout is not None:
        layout.activate()


class _CopyClicks(QObject):
    """Press-to-select on the wide copy.

    ``gesture.step`` hits the primary index. Drops and resizes stay there.
    """

    def __init__(self, session: FormSession, realizer: Realizer) -> None:
        super().__init__()
        self._session = session
        self._realizer = realizer
        self._watched: List[QWidget] = []

    def arm(self, root: QWidget) -> None:
        self.clear()
        self._watch(root)
        for child in root.findChildren(QWidget):
            self._watch(child)

    def clear(self) -> None:
        for widget in self._watched:
            if wrapper_is_valid(widget):
                widget.removeEventFilter(self)
        self._watched = []

    def _watch(self, widget: QWidget) -> None:
        widget.installEventFilter(self)
        self._watched.append(widget)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not _is_left_press(event):
            return False
        node = self._realizer.node_for(watched)
        if node is None:
            return False
        self._session.selection.set((node,), source=SelectionSource.CANVAS)
        return False


def _is_left_press(event: QEvent) -> bool:
    press = getattr(getattr(QEvent, "Type", QEvent), "MouseButtonPress")
    if event.type() != press:
        return False
    button = getattr(event, "button", None)
    if not callable(button):
        return False
    return enum_value(button()) == enum_value(getattr(Qt, "LeftButton"))
