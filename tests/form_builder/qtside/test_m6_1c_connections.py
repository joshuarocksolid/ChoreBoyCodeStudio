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
from app.features.form_builder.engine.logic.events_codec import slot_step, write_list
from app.features.form_builder.integration import keys_ext
from app.features.form_builder.integration.overlay_ext import connections as overlay
from app.features.form_builder.integration.workbench_ext.connections import layer_plan
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, Size, ViewMap
from app.features.form_builder.qtside.canvas.layers.connections import (
    LINK,
    ArrowState,
    build_arrows,
    curve,
    drawable_steps,
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
