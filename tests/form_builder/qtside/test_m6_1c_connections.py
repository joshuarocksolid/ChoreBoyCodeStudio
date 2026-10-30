# pyright: reportAttributeAccessIssue=false
"""M6.1c canvas connections: both storage forms, one SetEventSteps write, Esc, F4.

Clauses: UX-ARR-001 (badge tip and zoom), UX-ARR-002 (plain steps, dashed incoming),
UX-ARR-003 (curve ends 2 px outside), UX-ARR-005 (Show all scope), UX-ARR-006 (F4
toggles the overlay), UX-ARR-007 (nothing is written until a slot is chosen).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import call_step, slot_step, write_list
from app.features.form_builder.integration import keys_ext
from app.features.form_builder.integration.overlay_ext import connections as overlay
from app.features.form_builder.integration.workbench_ext.connections import layer_plan
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, Size, ViewMap
from app.features.form_builder.qtside.canvas.layers.connections import (
    LINK,
    ArrowState,
    build_arrows,
    curve,
    drawable_steps,
    mark_at,
)
from app.features.form_builder.qtside.canvas.layers.logic_badges import badge_tip, build as build_badges
from app.features.form_builder.integration.workbench_ext.connections import links_for
from app.qt.QtCore import QPointF, QTimer, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.unit.features.form_builder.test_workbench import _open
from tests.form_builder.engine.commands._support import open_log, saved

pytestmark = pytest.mark.unit


def form(extra_connections: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Sale</class>\n'
        ' <widget class="QDialog" name="Sale">\n'
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        '   <item>\n    <widget class="QPushButton" name="clearButton"/>\n   </item>\n'
        '   <item>\n    <widget class="QLineEdit" name="nameEdit"/>\n   </item>\n'
        '   <item>\n    <widget class="QLineEdit" name="phoneEdit"/>\n   </item>\n'
        "  </layout>\n </widget>\n <resources/>\n <connections>\n"
        + extra_connections
        + " </connections>\n</ui>\n"
    )


def connection(sender: str, signal: str, receiver: str, slot: str) -> str:
    return (
        "  <connection>\n   <sender>%s</sender>\n   <signal>%s</signal>\n"
        "   <receiver>%s</receiver>\n   <slot>%s</slot>\n  </connection>\n"
    ) % (sender, signal, receiver, slot)


class _Notes:
    def __init__(self, log: Any) -> None:
        self.session = SimpleNamespace(document=log.document, log=log)
        self.notes: list = []

    def narrate(self, text: str) -> None:
        self.notes.append(text)


class _DialogHost(QWidget):
    def __init__(self, log: Any) -> None:
        super().__init__()
        self.session = SimpleNamespace(document=log.document, log=log)
        self.notes: list = []

    def narrate(self, text: str) -> None:
        self.notes.append(text)


def _view(factor: float = 1.0) -> ViewMap:
    return ViewMap(factor, CanvasPoint(0, 0), Size(800, 600))


def _world(log: Any, current: Any, factor: float = 1.0) -> tuple:
    document = log.document
    placed = []
    x = 20
    for name in ("Sale", "clearButton", "nameEdit", "phoneEdit"):
        found = document.by_name(name)
        if found:
            placed.append(SimpleNamespace(node=found[0], rect=CanvasRect(x, 40, 80, 24)))
            x += 120
    static = SimpleNamespace(view=_view(factor), placed=tuple(placed), content=())
    inputs = SimpleNamespace(
        document=document,
        selection=SimpleNamespace(current=current),
        viewport=CanvasRect(0, 0, 800, 600),
        chrome=(),
        measure=lambda text: len(text) * 7,
    )
    return static, inputs


def test_curve_ends_two_pixels_outside_the_facing_edge() -> None:
    sender = CanvasRect(10, 10, 40, 20)
    receiver = CanvasRect(100, 10, 40, 20)
    start, _c1, _c2, end, head = curve(sender, receiver)
    assert start == (50, 20)
    assert end == (98, 20)
    assert head[0] == end


def test_a_connection_to_the_same_widget_leaves_the_top_edge() -> None:
    widget = CanvasRect(10, 30, 40, 20)
    start, _c1, _c2, end, _head = curve(widget, widget)
    assert start == (30, 30)
    assert end[0] == widget.x + widget.width + 2


def test_native_connections_and_step_lists_are_both_drawable() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    text = saved(log.document).replace(
        '<widget class="QLineEdit" name="phoneEdit"/>',
        '<widget class="QLineEdit" name="phoneEdit">\n    <property name="cbcsOnReturnPressed" stdset="0">'
        '<string notr="true">'
        + write_list((slot_step("nameEdit", "setFocus()"),)).replace('"', "&quot;")
        + "</string></property>\n   </widget>",
    )
    document = open_log(text).document
    drawn = drawable_steps(document)
    assert {(step.sender, step.signal, step.slot) for step in drawn} == {
        ("clearButton", "clicked()", "clear()"),
        ("phoneEdit", "returnPressed()", "setFocus()"),
    }


def test_a_turned_off_step_is_not_drawn() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (slot_step("nameEdit", "clear()", enabled=False),)))
    assert drawable_steps(log.document) == ()


def test_show_all_draws_the_selected_sender_strong_and_the_rest_faint() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    log.execute(SetEventSteps("phoneEdit", "returnPressed", (slot_step("nameEdit", "setFocus()"),)))
    current = log.document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    items = build_arrows(static, inputs, ArrowState("all"))
    weights = {}
    for item in items.items:
        data = getattr(item, "data", None)
        if isinstance(data, tuple) and data and data[0] == "arrow":
            weights[data[8]] = data[1]
    assert weights["clearButton"] == "strong"
    assert weights["phoneEdit"] == "faint"


def test_badges_name_the_events_and_hide_below_half_zoom() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    assert badge_tip(log.document, "clearButton") == "1 event: When clicked"
    current = log.document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    assert build_badges(static, inputs, True).items
    static.view = _view(0.4)
    assert build_badges(static, inputs, True).items == ()


@pytest.mark.parametrize(
    ("overlay", "behavior", "show_all", "badges", "scope"),
    [
        ("", False, False, True, None),
        ("", True, False, True, "selected"),
        ("", False, True, True, "all"),
        ("connections", True, False, False, "all"),
        ("tab_order", True, True, False, None),
        ("buddies", True, True, False, None),
        ("tab_order", True, False, False, None),
    ],
)
def test_layer_plan_keeps_show_all_when_f4_closes(
    overlay: str, behavior: bool, show_all: bool, badges: bool, scope: object
) -> None:
    assert layer_plan(True, overlay, behavior, show_all, True) == (badges, scope)


def test_finishing_a_link_is_one_undo_step_and_undo_restores_the_bytes() -> None:
    log = open_log(form())
    before = saved(log.document)
    host = _Notes(log)
    assert overlay.commit_step(host, "clearButton", "clicked()", slot_step("nameEdit", "clear()"), "nameEdit")
    assert len(log.entries()) == 1
    assert log.entries()[-1].label == "Connect clearButton to nameEdit"
    assert not overlay.commit_step(host, "clearButton", "clicked()", slot_step("nameEdit", "clear()"), "nameEdit")
    assert len(log.entries()) == 1
    assert log.undo()
    assert saved(log.document) == before and not log.entries()


def test_cancelling_the_picker_leaves_bytes_and_the_undo_stack(qapp: QApplication) -> None:
    del qapp
    log = open_log(form())
    before = saved(log.document)
    host = _DialogHost(log)
    document = log.document

    def reject() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is not None:
            dialog.reject()

    QTimer.singleShot(0, reject)
    overlay.choose_step(host, document.by_name("clearButton")[0], document.by_name("nameEdit")[0])
    assert saved(log.document) == before and not log.entries()


def test_f4_toggles_the_connections_overlay_and_show_all_is_ctrl_shift_l() -> None:
    seen = []
    surface = SimpleNamespace(toggle_overlay=lambda kind: seen.append(kind))
    handler = keys_ext.default_registry().handler("form.action.connections")
    assert handler is not None
    handler(surface)
    assert seen == ["connections"]
    rows = {command.command_id: command for command in keys_ext.default_registry().commands()}
    assert rows["form.action.showAllConnections"].shortcut == "Ctrl+Shift+L"
    assert rows["form.action.connectionLink"].shortcut == "Enter"
    assert rows["form.action.connectionForm"].shortcut == "Home"
    assert LINK == "connection_link"


def test_the_label_chip_sits_on_the_curve_not_in_a_margin_column() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    current = log.document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    items = build_arrows(static, inputs, ArrowState("all", ("clearButton", "clicked()", 0)))
    chips = [
        item
        for item in items.items
        if isinstance(getattr(item, "data", None), tuple) and item.data[0] == "chip" and item.data[2]
    ]
    assert len(chips) == 1
    assert chips[0].rect.x < 800
    assert abs((chips[0].rect.x + chips[0].rect.width / 2) - 240) < 80


class _Obstacle:
    def __init__(self, node: object, rect: CanvasRect, band: bool = False) -> None:
        self.node = node
        self.rect = rect
        self.band = band


def _sale_world(log: Any) -> tuple:
    """sale.ui widgets on the button row the gate photographed, plus the form layout as content."""
    document = log.document
    boxes = {
        "Sale": CanvasRect(0, 0, 520, 240),
        "nameLabel": CanvasRect(16, 16, 64, 22),
        "nameEdit": CanvasRect(96, 12, 200, 26),
        "phoneLabel": CanvasRect(16, 52, 64, 22),
        "phoneEdit": CanvasRect(96, 48, 200, 26),
        "clearButton": CanvasRect(16, 148, 88, 28),
        "printButton": CanvasRect(112, 148, 120, 28),
        "saveButton": CanvasRect(240, 148, 80, 28),
        "cancelButton": CanvasRect(328, 196, 72, 24),
        "buttonBox": CanvasRect(200, 190, 210, 36),
    }
    placed = []
    content = []
    for name, rect in boxes.items():
        found = document.by_name(name)
        assert found, name
        obstacle = _Obstacle(found[0], rect)
        placed.append(obstacle)
        content.append(obstacle)
    layout = document.root.layout
    assert layout is not None
    content.append(_Obstacle(layout.id, CanvasRect(8, 8, 500, 220)))
    content.append(_Obstacle(document.root.id, CanvasRect(0, 0, 520, 22), band=True))
    static = SimpleNamespace(view=_view(), placed=tuple(placed), content=tuple(content))
    current = document.by_name("clearButton")[0]
    inputs = SimpleNamespace(
        document=document,
        selection=SimpleNamespace(current=current, ids=(current,)),
        viewport=CanvasRect(0, 0, 800, 600),
        chrome=(),
        measure=lambda text: len(text) * 7,
    )
    return static, inputs, boxes


def test_sale_code_and_form_chips_cover_no_widget() -> None:
    text = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    log = open_log(text)
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (call_step("print_receipt"), slot_step("Sale", "accept()")),
        )
    )
    static, inputs, boxes = _sale_world(log)
    items = build_arrows(static, inputs, ArrowState("all", None)).items
    chips = [
        item
        for item in items
        if isinstance(item.data, tuple) and item.data[0] == "chip" and item.data[1] in ("code", "form")
    ]
    clear = [chip for chip in chips if chip.data[3] == "clearButton"]
    assert {chip.data[1] for chip in clear} == {"code", "form"}
    widgets = [boxes[name] for name in boxes if name != "Sale"]
    for chip in chips:
        covered = [name for name, rect in boxes.items() if name != "Sale" and chip.rect.intersects(rect)]
        assert not covered, (chip.data[1], chip.data[2], covered, chip.rect)


def test_chips_paint_above_every_arrow_and_leader() -> None:
    """UX-ARR-003: arrows are drawn below chips and never cross one."""
    text = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    log = open_log(text)
    log.execute(
        SetEventSteps("clearButton", "clicked", (call_step("print_receipt"), slot_step("Sale", "accept()")))
    )
    static, inputs, _boxes = _sale_world(log)
    items = build_arrows(static, inputs, ArrowState("all", None)).items
    kinds = [item.data[0] for item in items if isinstance(item.data, tuple)]
    assert "chip" in kinds
    first_chip = kinds.index("chip")
    assert all(kind == "chip" for kind in kinds[first_chip:]), kinds


def test_button_box_form_chips_sit_beside_the_button_box() -> None:
    """UX-ARR-004: a form chip is in the gutter next to its sender, on the sender's row."""
    text = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    log = open_log(text)
    static, inputs, boxes = _sale_world(log)
    items = build_arrows(static, inputs, ArrowState("all", None)).items
    chips = [
        item
        for item in items
        if isinstance(item.data, tuple) and item.data[0] == "chip" and item.data[1] == "form" and item.data[3] == "buttonBox"
    ]
    assert chips
    box = boxes["buttonBox"]
    for chip in chips:
        assert chip.rect.y < box.y + box.height and chip.rect.y + chip.rect.height > box.y, (chip.rect, box)
        covered = [name for name, rect in boxes.items() if name != "Sale" and chip.rect.intersects(rect)]
        assert not covered, covered


def test_hovering_a_sale_step_keeps_its_label_chip() -> None:
    text = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    log = open_log(text)
    log.execute(SetEventSteps("clearButton", "clicked", (slot_step("nameEdit", "clear()"),)))
    static, inputs, _boxes = _sale_world(log)
    drawn = drawable_steps(log.document)
    step = next(item for item in drawn if item.sender == "clearButton" and item.kind == "widget")
    items = build_arrows(static, inputs, ArrowState("all", (step.sender, step.signal, step.index))).items
    chips = [
        item
        for item in items
        if isinstance(item.data, tuple) and item.data[0] == "chip" and item.data[1] == "label" and item.data[2]
    ]
    assert len(chips) == 1
    assert "clear" in str(chips[0].data[2]).lower() or "name" in str(chips[0].data[2]).lower()


def test_a_click_nearer_arrow_a_aims_a() -> None:
    def arrow(x: int, sender: str) -> LayerItem:
        point = (x, 0)
        return LayerItem(
            CanvasRect(x, 0, 1, 1),
            "select",
            1.0,
            "connections",
            ("arrow", "faint", False, point, point, point, point, (point, point, point), sender, "clicked()", 0),
        )

    items = [arrow(0, "A"), arrow(8, "B")]
    aimed = mark_at(items, 2, 0)
    assert aimed is not None and aimed.sender == "A"
    other = mark_at(items, 6, 0)
    assert other is not None and other.sender == "B"


def test_an_aimed_arrow_is_the_heavy_stroke_and_keeps_its_label() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    current = log.document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    items = build_arrows(static, inputs, ArrowState("all", None, ("clearButton", "clicked()", 0))).items
    arrows = [item for item in items if isinstance(item.data, tuple) and item.data[0] == "arrow"]
    labels = [
        item
        for item in items
        if isinstance(item.data, tuple) and item.data[0] == "chip" and item.data[2]
    ]
    assert arrows and arrows[0].data[1] == "aimed"
    assert len(labels) == 1


def test_badges_stay_off_neighbours_and_the_title_band() -> None:
    text = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    log = open_log(text)
    log.execute(SetEventSteps("phoneEdit", "returnPressed", (slot_step("nameEdit", "setFocus()"),)))
    log.execute(SetEventSteps("buttonBox", "accepted", (slot_step("Sale", "accept()"),)))
    static, inputs, boxes = _sale_world(log)
    badges = {
        item.data[1]: item.rect
        for item in build_badges(static, inputs, None).items
        if isinstance(item.data, tuple) and item.data[0] == "badge"
    }
    band = CanvasRect(0, 0, 520, 22)
    for rect in badges.values():
        assert not rect.intersects(band)
    assert "phoneEdit" in badges and "buttonBox" in badges
    assert not badges["phoneEdit"].intersects(boxes["nameEdit"])
    overlap = min(badges["phoneEdit"].x + badges["phoneEdit"].width, boxes["phoneEdit"].x + boxes["phoneEdit"].width) - max(
        badges["phoneEdit"].x, boxes["phoneEdit"].x
    )
    assert overlap >= badges["phoneEdit"].width / 2
    assert not badges["buttonBox"].intersects(boxes["cancelButton"])
    assert badges["buttonBox"].x <= boxes["buttonBox"].x + 4


def test_an_unknown_glyph_falls_back_instead_of_raising(qapp: QApplication) -> None:
    del qapp
    from app.features.form_builder.integration.workbench import _glyph_icon

    assert _glyph_icon("not-a-real-glyph", "#000000", "#888888", 16, 1.0).isNull()
    assert not _glyph_icon("connections", "#000000", "#888888", 16, 1.0).isNull()


@pytest.mark.timeout(180)
def test_double_click_on_an_arrow_writes_nothing(qapp: QApplication, tmp_path: Path) -> None:
    text = form(connection("clearButton", "clicked()", "nameEdit", "clear()"))
    host = QWidget()
    surface = _open(host, text, tmp_path / "one.ui")
    host.show()
    surface.show()
    qapp.processEvents()
    before = saved(surface.session.document)
    links = links_for(surface)
    assert links is not None
    links.toggle_show_all()
    qapp.processEvents()
    canvas = surface.workbench.canvas
    point = _arrow_point(canvas, "clearButton")
    assert point is not None

    def reject() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is not None:
            dialog.reject()

    QTimer.singleShot(0, reject)
    QTest.mouseDClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    qapp.processEvents()
    assert QApplication.activeModalWidget() is None
    assert saved(surface.session.document) == before
    assert not surface.session.log.entries()
    qapp.processEvents()
    surface.release()
    host.close()


@pytest.mark.timeout(180)
def test_delete_on_an_aimed_arrow_is_one_undo_step(qapp: QApplication, tmp_path: Path) -> None:
    text = form(connection("clearButton", "clicked()", "nameEdit", "clear()"))
    host = QWidget()
    surface = _open(host, text, tmp_path / "one.ui")
    host.show()
    surface.show()
    qapp.processEvents()
    before = saved(surface.session.document)
    links = links_for(surface)
    assert links is not None
    links.toggle_show_all()
    qapp.processEvents()
    canvas = surface.workbench.canvas
    point = _arrow_point(canvas, "clearButton")
    assert point is not None
    canvas.setFocus()
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    qapp.processEvents()
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    qapp.processEvents()
    assert drawable_steps(surface.session.document) == ()
    entries = surface.session.log.entries()
    assert len(entries) == 1
    assert entries[0].label.startswith("Delete ")
    assert surface.undo()
    assert saved(surface.session.document) == before
    qapp.processEvents()
    surface.release()
    host.close()


def _arrow_point(canvas: QWidget, sender: str) -> object:
    for item in canvas.overlay().items:  # type: ignore[attr-defined]
        data = getattr(item, "data", None)
        if isinstance(data, tuple) and data and data[0] == "arrow" and data[8] == sender:
            rect = item.rect
            view = canvas.mapFromScene(QPointF(rect.x + rect.width / 2, rect.y + rect.height / 2))  # type: ignore[attr-defined]
            return canvas.viewport().mapFrom(canvas, view)  # type: ignore[attr-defined]
    return None


@pytest.mark.xfail(strict=True, reason="M6.1b opens the step picker on that step (UX-ARR-009)")
def test_double_click_opens_the_step_picker_on_that_step() -> None:
    from app.features.form_builder.qtside.pickers import open_for_step  # type: ignore[import-not-found]

    assert callable(open_for_step)


@pytest.mark.xfail(strict=True, reason="M6.1b owns qtside/pickers.open_for_link, the event picker and the step picker")
def test_link_opens_the_m6_1b_pickers() -> None:
    from app.features.form_builder.qtside.pickers import open_for_link  # type: ignore[import-not-found]

    assert overlay.active_picker() is open_for_link
