# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The free-placement grid on the canvas (UX-FSET-006): the step, the dots, and the key and drag code that must follow it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormGrid
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
from app.features.form_builder.qtside.canvas.core.snap import DEFAULT_STEP, GridStep, grid_step, snap_move
from app.features.form_builder.qtside.canvas.core.space import FormPoint
from app.features.form_builder.qtside.canvas.layers.free_grid import NAME, FreeGrid
from tests.form_builder.engine.commands._support import open_log
from tests.form_builder.inspector.m5_5b_support import LAID_OUT, free_form
from tests.form_builder.qtside.test_canvas_keys import _click, _drag, _shown, _widget, _key

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

FREE_PAGE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
    ' <widget class="QWidget" name="Form">\n'
    '  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>480</height></rect></property>\n'
    '  <widget class="QFrame" name="north">\n'
    '   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>40</height></rect></property>\n'
    '  </widget>\n </widget>\n'
    ' <designerdata>\n'
    '  <property name="gridDeltaX">\n   <number>16</number>\n  </property>\n'
    '  <property name="gridDeltaY">\n   <number>16</number>\n  </property>\n'
    ' </designerdata>\n</ui>\n'
)


def test_the_step_is_the_forms_and_snapping_off_lands_on_whole_pixels() -> None:
    assert grid_step(open_log(free_form()).document) == DEFAULT_STEP == GridStep(8, 8, True)
    doc = open_log(FREE_PAGE).document
    step = grid_step(doc)
    assert (step.across, step.down, step.snap) == (16, 16, True)
    origin = RectValue(40, 40, 80, 40)
    assert snap_move(origin, FormPoint(14, 14), True, step) == (8, 8)  # 54 -> 48
    assert snap_move(origin, FormPoint(14, 14), True) == (16, 16)  # the 8 px default: 54 -> 56
    assert snap_move(origin, FormPoint(14, 14), False, step) == (14, 14)  # Shift: no snap
    log = open_log(FREE_PAGE)
    log.execute(SetFormGrid("snap", False))
    assert snap_move(origin, FormPoint(14, 14), True, grid_step(log.document)) == (14, 14)


def test_the_step_nudge_is_one_step_or_one_pixel_with_shift() -> None:
    assert GridStep(16, 4).nudge(False) == (16, 4)
    assert GridStep(16, 4).nudge(True) == (1, 1)


def test_alt_arrow_moves_a_free_widget_by_the_forms_step() -> None:
    with _shown(FREE_PAGE) as (session, canvas):
        _click(canvas, "north")
        north = _widget(canvas, "north")
        assert north.x() == 40
        _key(canvas, "Key_Right", "AltModifier")
        assert north.x() == 56


def test_a_drag_in_a_free_container_lands_on_the_forms_step() -> None:
    with _shown(FREE_PAGE) as (session, canvas):
        _click(canvas, "north")
        _drag(canvas, 60, 60, 74, 60)
        assert _widget(canvas, "north").x() == 48


# ---- the dots -------------------------------------------------------------------------------------------------


def _open_big(path: Path, text: str):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QApplication, QVBoxLayout, QWidget
    from tests.unit.features.form_builder.test_workbench import _open

    host = QWidget()
    box = QVBoxLayout(host)
    box.setContentsMargins(0, 0, 0, 0)
    surface = _open(host, text, path)
    box.addWidget(surface)
    host.resize(1400, 900)
    host.show()
    for _ in range(4):
        QApplication.processEvents()
    return host, surface


def _drawn(canvas):  # type: ignore[no-untyped-def]
    controller = canvas._controller
    controller._pre_paint()
    return [item for item in controller.frame.items if isinstance(item, LayerItem) and item.layer == NAME]


@pytest.mark.parity("R3-222")
def test_the_dot_grid_follows_the_form_settings(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QWidget
    from tests.unit.features.form_builder.test_workbench import _open

    host = QWidget()
    surface = _open(host, free_form(), tmp_path / "till.ui")
    try:
        canvas = surface.workbench.canvas
        session = surface.session
        assert canvas.layer_state(NAME) == FreeGrid(8, 8)
        found = _drawn(canvas)
        assert len(found) == 1 and found[0].data[0] > 0  # type: ignore[index]  # pyright: ignore[reportIndexIssue]
        session.log.execute(SetFormGrid("across", 16))
        session.log.execute(SetFormGrid("down", 4))
        assert canvas.layer_state(NAME) == FreeGrid(16, 4)
        session.log.execute(SetFormGrid("show", False))
        assert canvas.layer_state(NAME) is None and _drawn(canvas) == []
        session.log.undo()
        assert canvas.layer_state(NAME) == FreeGrid(16, 4)
    finally:
        surface.release()
        host.close()


def test_a_form_with_every_container_laid_out_has_no_dots(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QWidget
    from tests.unit.features.form_builder.test_workbench import _open

    host = QWidget()
    surface = _open(host, LAID_OUT, tmp_path / "till.ui")
    try:
        assert surface.workbench.canvas.layer_state(NAME) is None
    finally:
        surface.release()
        host.close()


def test_the_dots_skip_children_and_paint_inside_the_container(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.qtside.canvas.layers.free_grid import paint
    from app.features.form_builder.qtside.theme import overlay as theme
    from app.qt.QtGui import QImage, QPainter

    host, surface = _open_big(tmp_path / "till.ui", free_form())
    try:
        found = _drawn(surface.workbench.canvas)[0]
        across, down, left, top, holes = found.data  # pyright: ignore[reportGeneralTypeIssues]
        assert len(holes) == 2 and holes[0][2] > 0
        fill, dot = theme.backdrop_fill(False, False)
        palette = theme.CanvasPalette(
            overlay=theme.overlay_palette(False),
            backdrop=theme.BackdropPalette(
                fill=fill, dot=dot, faint="#666F76", accent="#3366FF", muted="#5A6168",
                panel="#FFFFFF", border="#DEE2E6", text="#212529",
            ),
        )
        size = 800
        image = QImage(size, size, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
        image.fill(0)
        painter = QPainter(image)
        try:
            paint(painter, found, palette)
        finally:
            painter.end()
        rect = found.rect
        painted = [(x, y) for x in range(rect.x, rect.x + rect.width) for y in range(rect.y, rect.y + rect.height)
                   if 0 <= x < size and 0 <= y < size and image.pixelColor(x, y).alpha() > 0]
        assert painted, "the dots are drawn"
        assert all(rect.x <= x < rect.x + rect.width and rect.y <= y < rect.y + rect.height for x, y in painted)
        for hx, hy, hw, hh in holes:
            assert not any(hx + 2 <= x < hx + hw - 2 and hy + 2 <= y < hy + hh - 2 for x, y in painted), "no dot under a child"
        # High contrast has no dots, as the backdrop has none.
        flat = theme.CanvasPalette(overlay=theme.overlay_palette(True), backdrop=theme.BackdropPalette(
            fill="#000000", dot="", faint="#FFFFFF", accent="#FFFF00", muted="#FFFFFF", panel="#000000", border="#FFFFFF", text="#FFFFFF"))
        image.fill(0)
        painter = QPainter(image)
        try:
            paint(painter, found, flat)
        finally:
            painter.end()
        assert not any(image.pixelColor(x, y).alpha() for x in range(0, size, 3) for y in range(0, size, 3))
    finally:
        surface.release()
        host.close()
