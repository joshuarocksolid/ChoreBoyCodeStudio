"""Logic badges (UX-ARR-001). One 12 px mark per sender that has an event.

The workbench shows this layer in Design. ``build`` returns nothing below
50% zoom. Preview, Save image and Print never ask this layer to paint.
"""

from __future__ import annotations

from typing import Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.events import events_of_sender, read_events
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.engine.style.classes import widget_chain
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.canvas.core.chips import BADGE_CORNERS, ChipRequest, place_chips
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter

NAME = "logic_badges"
BADGE = 12
HIDE_BELOW = 0.5


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, paint, order=74))


def badge_tip(doc: UiDocument, sender: str) -> str:
    """``{n} events: When clicked, When toggled``, then ``and {k} more``."""
    states = events_of_sender(doc, sender)
    chain = _chain(doc, sender)
    words = ["When %s" % event_words(state.signal_name, chain).header for state in states]
    shown = words[:3]
    extra = len(words) - len(shown)
    text = "%d events: %s" % (len(words), ", ".join(shown))
    if extra:
        text += " and %d more" % extra
    return text


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    del state
    view = getattr(static, "view", None)
    factor = float(getattr(view, "factor", 1.0) or 1.0)
    if factor < HIDE_BELOW:
        return LayerOutput()
    document = getattr(inputs, "document")
    senders = []
    seen = set()
    for event in read_events(document):
        if event.sender not in seen:
            seen.add(event.sender)
            senders.append(event.sender)
    if not senders:
        return LayerOutput()
    placed = {}
    for item in getattr(static, "placed", ()):
        placed[item.node] = item.rect
    page = _page(static)
    viewport = getattr(inputs, "viewport", None) or page
    if page is None or viewport is None:
        return LayerOutput()
    requests = []
    tips = {}
    widget_rect = {}
    for sender in senders:
        found = document.by_name(sender)
        rect = placed.get(found[0]) if found else None
        if rect is None:
            continue
        tips[sender] = badge_tip(document, sender)
        widget_rect[sender] = rect
        requests.append(ChipRequest(sender, rect, CanvasSize(BADGE, BADGE), BADGE_CORNERS, frozenset()))
    if not requests:
        return LayerOutput()
    seats = place_chips(
        requests,
        tuple(getattr(static, "content", ())),
        tuple(getattr(inputs, "chrome", ())),
        page,
        viewport,
    )
    seated = {str(seat.key): seat.rect for seat in seats}
    items: List[LayerItem] = []
    for sender, rect in widget_rect.items():
        items.append(
            LayerItem(
                rect=seated.get(sender) or _badge_fallback(rect, page),
                role="select",
                layer=NAME,
                data=("badge", sender, tips.get(sender, "")),
            )
        )
    return LayerOutput(tuple(items))


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data or data[0] != "badge":
        return
    fill = _qcolor(palette.overlay.logic_badge)
    ink = _qcolor(palette.overlay.chip_text)
    box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(box)
        painter.setPen(ink)
        font = QFont(painter.font())
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "›")
    finally:
        painter.restore()


def mark_at(items: Sequence[object], x: float, y: float) -> Optional[str]:
    """The sender name when ``(x, y)`` is inside a badge."""
    point = CanvasPoint(int(x), int(y))
    for item in reversed(tuple(items)):
        if not isinstance(item, LayerItem):
            continue
        data = item.data
        if isinstance(data, tuple) and data and data[0] == "badge" and item.rect.contains(point):
            return str(data[1])
    return None


def tip_at(items: Sequence[object], x: float, y: float) -> str:
    point = CanvasPoint(int(x), int(y))
    for item in reversed(tuple(items)):
        if not isinstance(item, LayerItem):
            continue
        data = item.data
        if isinstance(data, tuple) and data and data[0] == "badge" and item.rect.contains(point):
            return str(data[2])
    return ""


def _chain(doc: UiDocument, sender: str) -> Tuple[str, ...]:
    found = doc.by_name(sender)
    node = doc.node(found[0]) if found else None
    if not isinstance(node, WidgetNode):
        return ()
    return widget_chain(doc, node)


def _badge_fallback(rect: CanvasRect, page: Optional[CanvasRect]) -> CanvasRect:
    """Top-right, just outside the widget. Inside the corner when that would leave the page."""
    x = rect.x + rect.width - 2
    y = rect.y - BADGE - 2
    if page is not None and y < page.y:
        x = rect.x + max(0, rect.width - BADGE - 2)
        y = rect.y + 2
    return CanvasRect(x, y, BADGE, BADGE)


def _page(static: object) -> Optional[CanvasRect]:
    view = getattr(static, "view", None)
    origin = getattr(view, "page_origin", None)
    page = getattr(view, "page", None)
    if origin is None or page is None:
        return None
    return CanvasRect(origin.x, origin.y, page.width, page.height)


def _qcolor(text: str) -> QColor:
    raw = text.lstrip("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    alpha = int(raw[6:8], 16) if len(raw) >= 8 else 255
    return QColor(red, green, blue, alpha)
