"""Canvas overlay layers (M5.0s): extra marks a lane draws on the canvas.

A layer is a module in this package that exposes ``register(registry)`` and
calls ``registry.add(CanvasLayer(...))``. Modules are discovered in sorted
name order; a module whose name starts with an underscore is a helper. A lane
adds its file and edits neither ``paint.py`` nor ``core/overlay.py``.

A layer has a Qt-free ``build(static, inputs, state) -> LayerOutput`` that returns
items and hit targets, and optionally a ``paint(painter, item, palette)`` for
a ``LayerItem`` it made. Plain ``Stroke``, ``Fill``, ``Chip``, ``Badge`` and
``Caption`` items need no painter. Items sit above the built-in marks and below
the chips; a layer's targets win over the built-in ones.

A canvas runs only the layers switched on for it. A lane switches its layer
on for one canvas with ``canvas.show_layer(name, state)`` (``FormCanvas``, or
the ``CanvasController`` behind it) and off with ``canvas.hide_layer(name)``;
calling ``show_layer`` again with a new state redraws the overlay. ``state``
is any hashable value the layer's ``build`` needs (``True`` when it needs
none). The controller passes ``registry.resolve(states)`` to
``FrameInputs.layers``. With no layer on, a frame pays one empty-tuple test
and ``paint_frame`` pays nothing. Order of layers: ``(order, name)``.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Dict, Hashable, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.features.form_builder.qtside.canvas.core.overlay import ActiveLayer, LayerItem, LayerOutput, OverlayLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtGui import QPainter

logger = logging.getLogger(__name__)

LayerPaint = Callable[[QPainter, LayerItem, CanvasPalette], None]


@dataclass(frozen=True)
class CanvasLayer:
    name: str
    build: OverlayLayer
    paint: Optional[LayerPaint] = None
    order: int = 100


class LayerRegistry:
    def __init__(self) -> None:
        self._layers: Dict[str, CanvasLayer] = {}

    def add(self, layer: CanvasLayer) -> None:
        if not layer.name:
            raise ValueError("a canvas layer needs a name")
        if layer.name in self._layers:
            raise ValueError("canvas layer %s is already registered" % layer.name)
        self._layers[layer.name] = layer

    def names(self) -> Tuple[str, ...]:
        return tuple(layer.name for layer in self._ordered(self._layers.values()))

    def resolve(self, states: Mapping[str, Hashable]) -> Tuple[ActiveLayer, ...]:
        """The layers named in ``states`` with their state, in layer order. A name nobody registered is skipped."""
        wanted = [self._layers[name] for name in states if name in self._layers]
        return tuple(ActiveLayer(layer.name, layer.build, states[layer.name]) for layer in self._ordered(wanted))

    def painter(self, name: str) -> Optional[LayerPaint]:
        layer = self._layers.get(name)
        return layer.paint if layer is not None else None

    @staticmethod
    def _ordered(layers: Iterable[CanvasLayer]) -> List[CanvasLayer]:
        return sorted(layers, key=lambda layer: (layer.order, layer.name))


def load_layers(*packages: ModuleType) -> LayerRegistry:
    registry = LayerRegistry()
    run_contributors("canvas layer", packages, "register", lambda _module, hook: hook(registry))
    return registry


_DEFAULT: Optional[LayerRegistry] = None


def default_registry() -> LayerRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_layers(sys.modules[__name__])
    return _DEFAULT


def paint_layer_item(
    painter: QPainter,
    item: LayerItem,
    palette: CanvasPalette,
    fallback: Callable[[QPainter, LayerItem, CanvasPalette], None],
) -> None:
    """Paint ``item`` with its layer's painter, or as a plain fill when the layer has none."""
    paint = default_registry().painter(item.layer)
    if paint is None:
        fallback(painter, item, palette)
        return
    try:
        paint(painter, item, palette)
    except Exception:
        logger.exception("canvas layer %s could not paint", item.layer)


__all__: Sequence[str] = [
    "ActiveLayer",
    "CanvasLayer",
    "LayerItem",
    "LayerOutput",
    "LayerPaint",
    "LayerRegistry",
    "default_registry",
    "load_layers",
    "paint_layer_item",
]
