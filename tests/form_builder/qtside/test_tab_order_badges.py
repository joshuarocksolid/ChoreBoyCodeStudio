"""Tab-order badge geometry. The number sits on the widget's right edge."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, Tuple

import pytest

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers.tab_order import TabOrderState, build

pytestmark = [pytest.mark.unit]

_ORIGIN_X = 10
_ORIGIN_Y = 30


def _items(rects: Dict[str, CanvasRect]) -> Tuple[object, ...]:
    nodes = {name: NodeId(index) for index, name in enumerate(rects, start=1)}

    def by_name(name: str) -> Tuple[NodeId, ...]:
        found = nodes.get(name)
        return (found,) if found is not None else ()

    static = SimpleNamespace(
        placed=tuple(SimpleNamespace(node=nodes[name], rect=rect) for name, rect in rects.items()),
        view=SimpleNamespace(page_rect=lambda: CanvasRect(0, 0, 800, 600)),
        content=(),
    )
    inputs = SimpleNamespace(
        document=SimpleNamespace(by_name=by_name),
        viewport=CanvasRect(0, 0, 800, 600),
        measure=lambda _text: 10,
        chrome=(),
    )
    return build(static, inputs, TabOrderState(order=tuple(rects))).items


def _kind(item: LayerItem) -> str:
    data = item.data
    if isinstance(data, tuple) and data:
        return str(data[0])
    return ""


def _badges(rects: Dict[str, CanvasRect]) -> Tuple[LayerItem, ...]:
    return tuple(item for item in _items(rects) if isinstance(item, LayerItem) and _kind(item) == "badge")


@pytest.mark.parametrize(
    ("width", "height", "x", "y"),
    (
        (120, 24, 110, 34),
        (48, 24, 38, 34),
        (47, 24, 61, 34),
        (20, 10, 34, 27),
    ),
)
def test_tab_order_badge_sits_on_the_right_edge(width: int, height: int, x: int, y: int) -> None:
    (badge,) = _badges({"amount": CanvasRect(_ORIGIN_X, _ORIGIN_Y, width, height)})
    assert badge.rect == CanvasRect(x, y, 16, 16)
    assert badge.data == ("badge", 1, True, ())


def test_tab_order_flow_joins_badge_centres() -> None:
    items = _items(
        {
            "amount": CanvasRect(10, 30, 120, 24),
            "code": CanvasRect(10, 80, 40, 20),
        }
    )
    badges = [item for item in items if isinstance(item, LayerItem) and _kind(item) == "badge"]
    flows = [item for item in items if isinstance(item, LayerItem) and _kind(item) == "flow"]
    assert len(flows) == 1
    centres = [
        (float(item.rect.x + item.rect.width // 2), float(item.rect.y + item.rect.height // 2)) for item in badges
    ]
    payload = flows[0].data
    assert isinstance(payload, tuple)
    segments = payload[1]
    assert isinstance(segments, tuple) and segments
    step = segments[0]
    assert isinstance(step, tuple)
    x1, y1, _cx, _cy, x2, y2 = step
    assert (x1, y1) == centres[0]
    assert (x2, y2) == centres[1]
