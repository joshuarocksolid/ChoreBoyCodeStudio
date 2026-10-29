# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Canvas overlay layers: a module in layers/ adds marks and targets, and an idle canvas pays nothing."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

import app.features.form_builder.qtside.canvas.layers as layers
from app.features.form_builder.qtside.canvas.core.frame import OnSpace, Stroke
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, build_frame, build_static
from app.features.form_builder.qtside.canvas.core.gesture import Idle
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.qtside.canvas.paint import paint_frame
from app.features.form_builder.qtside.theme import overlay as theme
from app.qt.QtCore import QRectF
from app.qt.QtGui import QImage, QPainter
from tests.form_builder.m5_0s_support import forget_package, make_package
from tests.form_builder.qtside.test_canvas_core import LAID, _entry, _index, _inputs, _nid, _opened, _view

pytestmark = [pytest.mark.unit]

_PACKAGE = "m5_layer_probe"

_PROBE = """
    from app.features.form_builder.qtside.canvas.core.frame import OnSpace, Stroke
    from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
    from app.features.form_builder.qtside.canvas.core.space import CanvasRect
    from app.features.form_builder.qtside.canvas.layers import CanvasLayer

    PAINTED = []

    def _build(static, inputs):
        root = inputs.document.root.id
        box = CanvasRect(10, 10, 40, 40)
        return LayerOutput(
            (Stroke(box, "problem", 2, "solid"), LayerItem(box, "select", 1.0, "probe", ("tag",))),
            ((box, OnSpace(root, root)),),
        )

    def _paint(painter, item, palette):
        PAINTED.append(item.data)

    def register(registry):
        registry.add(CanvasLayer("probe", _build, _paint, order=200))
"""

_BROKEN = """
    from app.features.form_builder.qtside.canvas.layers import CanvasLayer

    def _build(static, inputs):
        raise RuntimeError("lane bug")

    def register(registry):
        registry.add(CanvasLayer("broken", _build, order=100))
"""


@pytest.fixture()
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[layers.LayerRegistry]:
    package = make_package(tmp_path, monkeypatch, _PACKAGE, {"a_broken": _BROKEN, "b_probe": _PROBE})
    loaded = layers.load_layers(package)
    monkeypatch.setattr(layers, "_DEFAULT", loaded)
    yield loaded
    forget_package(_PACKAGE)


def _frame(registry: layers.LayerRegistry, names):  # type: ignore[no-untyped-def]
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        ok = _nid(session, "ok")
        index = _index(
            (_entry(form, "widget", (0, 0, 400, 300), None), _entry(ok, "widget", (20, 20, 100, 30), form))
        )
        static = build_static(session.document, index, view)
        inputs = _inputs(session, view, SelectionState(), Idle())
        plain = build_frame(static, inputs)
        layered = build_frame(static, replace(inputs, layers=registry.resolve(names)))
        return plain, layered, form


def test_discovery_orders_layers_and_a_name_nobody_registered_is_skipped(registry: layers.LayerRegistry) -> None:
    assert registry.names() == ("broken", "probe")
    assert len(registry.resolve(("probe", "nobody"))) == 1
    with pytest.raises(ValueError):
        registry.add(layers.CanvasLayer("probe", lambda static, inputs: layers.LayerOutput()))


def test_an_active_layer_adds_items_above_the_built_in_marks_and_wins_the_hit(  # type: ignore[no-untyped-def]
    registry: layers.LayerRegistry,
) -> None:
    plain, layered, form = _frame(registry, ("probe",))
    assert layered.items[: len(plain.items)] == plain.items
    extra = layered.items[len(plain.items) :]
    assert [type(item) for item in extra] == [Stroke, LayerItem]
    assert layered.targets[0][1] == OnSpace(form, form) and layered.targets[1:] == plain.targets


def test_no_active_layer_gives_the_identical_frame_and_a_broken_one_is_skipped(  # type: ignore[no-untyped-def]
    registry: layers.LayerRegistry,
) -> None:
    plain, none, _form = _frame(registry, ())
    assert none == plain
    plain, broken, _form = _frame(registry, ("broken",))
    assert broken == plain


def test_a_layer_item_is_painted_by_its_layer_and_a_layer_with_no_painter_draws_a_fill(  # type: ignore[no-untyped-def]
    registry: layers.LayerRegistry, qapp
) -> None:
    del qapp
    _plain, layered, _form = _frame(registry, ("probe",))
    fill, dot = theme.backdrop_fill(False, False)
    palette = theme.CanvasPalette(
        overlay=theme.overlay_palette(False),
        backdrop=theme.BackdropPalette(
            fill=fill, dot=dot, faint="#666F76", accent="#3366FF", muted="#5A6168",
            panel="#FFFFFF", border="#DEE2E6", text="#212529",
        ),
    )
    image = QImage(120, 120, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
    image.fill(0)
    painter = QPainter(image)
    try:
        paint_frame(painter, layered, palette, QRectF(0, 0, 120, 120))
        assert registry._layers["probe"].paint is not None
        assert __import__(_PACKAGE + ".b_probe", fromlist=["PAINTED"]).PAINTED == [("tag",)]
        orphan = LayerItem(layered.items[-1].rect, "select", 1.0, "nobody", None)
        image.fill(0)
        painter.end()
        painter = QPainter(image)
        paint_frame(painter, replace(layered, items=(orphan,)), palette, QRectF(0, 0, 120, 120))
    finally:
        painter.end()
    assert image.pixelColor(30, 30).alpha() > 0
