"""The page on the backdrop. The single owner of the page rect.

Root geometry in the document wins. This stage does not replace it with the
layout's size hint. Without that property the page is the hint grown to the
minimum, and that size is not saved.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QGraphicsProxyWidget, QGraphicsView, QLabel, QWidget
from app.qt.qt_compat import wrapper_is_valid

from app.features.form_builder.engine.commands.live import PropKey
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
from app.features.form_builder.qtside.canvas.core.words import page_chip_label
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import BackdropPalette

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
    "copy": "DragCopyCursor",
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
        on_factor: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._view = view
        self._session = session
        self._realizer = realizer
        self._invalidate = invalidate
        self._on_factor = on_factor
        self._zoom: ZoomSetting = Fit()
        self._factor = 0.0
        self._fit_page: Optional[Size] = None
        self._homed_viewport: Optional[Tuple[int, int]] = None
        self._ignored_geometry: Optional[Tuple[int, int]] = None
        self._banner_push = 0
        self._previewed: Tuple[PropKey, ...] = ()
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
        # The view follows the page's home scroll until the user or a reveal
        # scrolls it. Programmatic setValue does not emit actionTriggered.
        self._homed = True
        view.horizontalScrollBar().actionTriggered.connect(self._scrolled)
        view.verticalScrollBar().actionTriggered.connect(self._scrolled)

    @property
    def proxy(self) -> QGraphicsProxyWidget:
        return self._proxy

    def hold_fit_page(self, held: bool) -> None:
        """O(1). Fit keeps the page size from before a two-widths resize."""
        if held:
            root = self._realizer.root_widget
            if root is not None and self._fit_page is None:
                self._fit_page = Size(max(root.width(), 1), max(root.height(), 1))
            return
        self._fit_page = None

    def place(self) -> None:
        """Attach the root, keep a positive document size, and lay out the page."""
        root = self._attach()
        if root is None:
            return
        if self._settle_root_size(root):
            self._invalidate("root_resize")
        if not self._page_preview:
            page = self._fit_page if self._fit_page is not None else Size(root.width(), root.height())
            factor = zoom_factor(self._zoom, page, _viewport(self._view))
            if factor != self._factor:
                self._invalidate("zoom")
                self._factor = factor
                if self._on_factor is not None:
                    self._on_factor(factor)
        scale = self._factor or 1.0
        if abs(self._proxy.scale() - scale) > 1e-6:
            self._proxy.setScale(scale)
        if self._page_preview:
            self._grow_scene(root)
        else:
            placed = layout_page(
                Size(root.width(), root.height()),
                scale,
                _viewport(self._view),
                0,
            )
            origin = self._proxy.pos()
            moved = abs(origin.x() - placed.page_origin.x) > 0.5 or abs(origin.y() - placed.page_origin.y) > 0.5
            if moved:
                self._proxy.setPos(placed.page_origin.x, placed.page_origin.y)
            scene = self._view.scene()
            current = scene.sceneRect()
            resized = abs(current.width() - placed.scene.width) > 0.5 or abs(current.height() - placed.scene.height) > 0.5
            if resized:
                scene.setSceneRect(0, 0, placed.scene.width, placed.scene.height)
            viewport = _viewport(self._view)
            size = (viewport.width, viewport.height)
            if self._homed and (self._scroll_off_home(placed) or size != self._homed_viewport):
                self._go_home(placed)
                self._homed_viewport = size
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

    def chrome_widgets(self) -> Tuple[QWidget, ...]:
        """The page caption, name chip, and size readout. The toast stays off them."""
        widgets = [self._name, self._size, *self._extra]
        if self._dock is not None and self._dock not in widgets:
            widgets.append(self._dock)
        return tuple(widget for widget in widgets if not widget.isHidden() and widget.width() > 0)

    def chrome_rects(self) -> Tuple[CanvasRect, ...]:
        scroll_x = self._view.horizontalScrollBar().value()
        scroll_y = self._view.verticalScrollBar().value()
        rects = []
        for widget in (self._name, self._size, *self._extra):
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
        width = widget.width()
        name = self._name
        if not name.isHidden() and name.x() >= widget.x():
            width = max(width, name.x() + name.width() - widget.x())
        return CanvasRect(widget.x() + scroll_x, widget.y() + scroll_y, width, widget.height())

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
        self._name.move(
            top_left.x(),
            max(0, top_left.y() - self._banner_push - self._name.height() - 4),
        )
        self._name.raise_()
        size_x = top_left.x() + max(0, (bottom_right.x() - top_left.x() - self._size.width()) // 2)
        self._size.move(size_x, bottom_right.y() + 6)
        self._size.raise_()

    def seat_page_chip(self, title: QWidget) -> None:
        """O(1). A pinned caption keeps the page name at its right end, clear of the caption."""
        name = self._name
        _fit_label(name)
        gap = 6
        full = title.width()
        if name.width() + gap >= full:
            name.hide()
            return
        title.setFixedWidth(full - name.width() - gap)
        name.move(
            title.x() + title.width() + gap,
            title.y() + max(0, (title.height() - name.height()) // 2),
        )
        name.show()
        name.raise_()

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
            asked = (value.width, value.height)
            # A layout taller than the stored page ignores the resize. Calling it
            # again on every edit walks the form and invalidates the hit index.
            if asked == self._ignored_geometry:
                return False
            root.resize(value.width, value.height)
            if root.width() == width and root.height() == height:
                self._ignored_geometry = asked
                return False
            self._ignored_geometry = None
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
        if self._name.text() != label:
            self._name.setText(label)
            self._name.setAccessibleName(label)
        size = "%d × %d" % (root.width(), root.height())
        if self._size.text() != size:
            self._size.setText(size)

    def _scrolled(self, _action: int) -> None:
        self._homed = False
        self._homed_viewport = None

    def _scroll_off_home(self, placed: PagePlacement) -> bool:
        """O(1). True when the bars are not already showing the page's home."""
        horizontal = self._view.horizontalScrollBar().value()
        vertical = self._view.verticalScrollBar().value()
        return abs(horizontal - placed.home.x) > 1 or abs(vertical - placed.home.y) > 1

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
        """Mutate the live objects in place. No rebuild, and the hit index stays frozen."""
        keys = tuple(dict.fromkeys(prop.key for prop in effect.props))
        dropped = tuple(key for key in self._previewed if key not in keys)
        self._page_preview = False
        if dropped:
            self._realizer.reapply(dropped)
        self._realizer.apply_live(effect.props)
        self._previewed = keys

    def _run_preview_page(self, effect: PreviewPage) -> None:
        root = self._realizer.root_widget
        if root is None:
            return
        self._page_preview = True
        self._previewed = ((self._session.document.root.id, "geometry"),)
        root.resize(effect.size.width, effect.size.height)
        self._proxy.setScale(self._factor or 1.0)
        self._grow_scene(root)
        self._refresh_labels(root)
        self.position_labels()

    def _run_end_preview(self) -> None:
        keys = self._previewed
        self._previewed = ()
        self._page_preview = False
        if keys:
            self._realizer.reapply(keys)
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
    if label.property("cbcsFit") == text:
        return
    label.setProperty("cbcsFit", text)
    width = label.fontMetrics().horizontalAdvance(text) + 16
    height = max(22, label.fontMetrics().height() + 8)
    label.setFixedSize(max(width, 8), height)
