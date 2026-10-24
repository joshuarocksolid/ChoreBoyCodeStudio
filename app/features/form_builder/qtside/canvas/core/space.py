"""Form pixels and canvas pixels. Zoom scales the page. The view stays 1:1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional, Tuple, Union

from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.values import RectValue

Compass = Literal["n", "ne", "e", "se", "s", "sw", "w", "nw"]


@dataclass(frozen=True)
class FormPoint:
    x: float
    y: float


@dataclass(frozen=True)
class CanvasPoint:
    x: int
    y: int


@dataclass(frozen=True)
class PortPoint:
    """Viewport pixels. Scrolling does not move a port point."""

    x: int
    y: int


@dataclass(frozen=True)
class CanvasSize:
    width: int
    height: int


@dataclass(frozen=True)
class CanvasRect:
    x: int
    y: int
    width: int
    height: int

    def contains(self, point: CanvasPoint) -> bool:
        return (
            self.x <= point.x < self.x + self.width
            and self.y <= point.y < self.y + self.height
        )

    def intersects(self, other: "CanvasRect") -> bool:
        return (
            self.x < other.x + other.width
            and other.x < self.x + self.width
            and self.y < other.y + other.height
            and other.y < self.y + self.height
        )

    def grown(self, by: int) -> "CanvasRect":
        return CanvasRect(
            self.x - by,
            self.y - by,
            self.width + 2 * by,
            self.height + 2 * by,
        )


@dataclass(frozen=True)
class Size:
    width: int
    height: int


@dataclass(frozen=True)
class ViewMap:
    """Form to canvas. Scrolling does not change it."""

    factor: float
    page_origin: CanvasPoint
    page: Size

    def to_canvas(self, rect: Rect) -> CanvasRect:
        # Outward rounding keeps a stroke outside the widget off its edge pixels.
        left = self.page_origin.x + rect.x * self.factor
        top = self.page_origin.y + rect.y * self.factor
        right = self.page_origin.x + (rect.x + rect.width) * self.factor
        bottom = self.page_origin.y + (rect.y + rect.height) * self.factor
        x = math.floor(left)
        y = math.floor(top)
        return CanvasRect(x, y, math.ceil(right) - x, math.ceil(bottom) - y)

    def to_form(self, point: CanvasPoint) -> FormPoint:
        factor = self.factor if self.factor else 1.0
        return FormPoint(
            (point.x - self.page_origin.x) / factor,
            (point.y - self.page_origin.y) / factor,
        )

    def page_rect(self) -> CanvasRect:
        return CanvasRect(
            self.page_origin.x,
            self.page_origin.y,
            max(1, int(round(self.page.width * self.factor))),
            max(1, int(round(self.page.height * self.factor))),
        )


ZOOM_STEPS: Tuple[float, ...] = (
    0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0,
)
FIT_CAP = 1.0
# A new tab opens at Fit and never below 75%. A tighter page scrolls.
FIT_FLOOR = 0.75
# Widest elided chip (24 characters) plus padding and the gutter inset.
SIDE_GUTTER = 24 * 8 + 12 + 4


@dataclass(frozen=True)
class Fit:
    """Re-fit on pane resize until the user picks a zoom."""


@dataclass(frozen=True)
class Fixed:
    factor: float


ZoomSetting = Union[Fit, Fixed]


@dataclass(frozen=True)
class ZoomStep:
    direction: int


@dataclass(frozen=True)
class ZoomTo:
    factor: float


@dataclass(frozen=True)
class ZoomFit:
    pass


ZoomChange = Union[ZoomStep, ZoomTo, ZoomFit]


@dataclass(frozen=True)
class Gutters:
    left: int = SIDE_GUTTER
    right: int = SIDE_GUTTER
    top: int = 64
    bottom: int = 64


GUTTERS = Gutters()


def apply_zoom(setting: ZoomSetting, change: ZoomChange, current: float) -> ZoomSetting:
    if isinstance(change, ZoomFit):
        return Fit()
    if isinstance(change, ZoomTo):
        return Fixed(change.factor)
    if change.direction == 0:
        return setting
    return Fixed(_neighbour(current, change.direction))


def zoom_factor(setting: ZoomSetting, page: Size, viewport: CanvasSize) -> float:
    if isinstance(setting, Fixed):
        return setting.factor
    return _fit_factor(page, viewport)


@dataclass(frozen=True)
class PagePlacement:
    scene: CanvasSize
    page_origin: CanvasPoint


def layout_page(
    page: Size, factor: float, viewport: CanvasSize, banner_push: int
) -> PagePlacement:
    scaled_w = max(1, int(round(page.width * factor)))
    scaled_h = max(1, int(round(page.height * factor)))
    needed_w = scaled_w + GUTTERS.left + GUTTERS.right
    needed_h = scaled_h + GUTTERS.top + GUTTERS.bottom
    if needed_w <= viewport.width:
        x = (viewport.width - scaled_w) // 2
    else:
        x = GUTTERS.left
    if needed_h <= viewport.height:
        y = (viewport.height - scaled_h) // 2
    else:
        y = GUTTERS.top
    y += banner_push
    scene = CanvasSize(
        max(viewport.width, x + scaled_w + GUTTERS.right),
        max(viewport.height, y + scaled_h + GUTTERS.bottom),
    )
    return PagePlacement(scene, CanvasPoint(x, y))


def anchored_scroll(
    before: ViewMap, after: ViewMap, anchor: CanvasPoint, scroll: CanvasPoint
) -> CanvasPoint:
    """Scroll that keeps the form point under ``anchor`` fixed. ``anchor`` is viewport pixels."""
    form = before.to_form(CanvasPoint(scroll.x + anchor.x, scroll.y + anchor.y))
    canvas_x = after.page_origin.x + form.x * after.factor
    canvas_y = after.page_origin.y + form.y * after.factor
    return CanvasPoint(int(round(canvas_x - anchor.x)), int(round(canvas_y - anchor.y)))


def page_request(
    document_geometry: Optional[RectValue], hint: Size, minimum: Size
) -> Optional[Size]:
    """None when a positive document geometry already owns the root size.

    The realizer applied that width and height. ``Stage`` must not replace it
    with the size hint. Without a positive geometry the page is the hint grown
    to the layout minimum, and that size is not saved.
    """
    if (
        document_geometry is not None
        and document_geometry.width > 0
        and document_geometry.height > 0
    ):
        return None
    return Size(max(hint.width, minimum.width), max(hint.height, minimum.height))


def _neighbour(current: float, direction: int) -> float:
    if direction > 0:
        for step in ZOOM_STEPS:
            if step > current + 1e-9:
                return step
        return ZOOM_STEPS[-1]
    for step in reversed(ZOOM_STEPS):
        if step < current - 1e-9:
            return step
    return ZOOM_STEPS[0]


def _fit_factor(page: Size, viewport: CanvasSize) -> float:
    avail_w = viewport.width - GUTTERS.left - GUTTERS.right
    avail_h = viewport.height - GUTTERS.top - GUTTERS.bottom
    if page.width <= 0 or page.height <= 0 or avail_w <= 0 or avail_h <= 0:
        return FIT_FLOOR
    factor = min(avail_w / page.width, avail_h / page.height)
    if factor < FIT_FLOOR:
        return FIT_FLOOR
    if factor > FIT_CAP:
        return FIT_CAP
    return factor
