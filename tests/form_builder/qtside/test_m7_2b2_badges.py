# pyright: reportAttributeAccessIssue=false
"""Rule badges and the arrows from a name a formula reads."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.qt.QtWidgets import QApplication

from app.features.form_builder.integration.workbench_ext.connections import layer_plan
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, Size, ViewMap
from app.features.form_builder.qtside.canvas.layers.feeds import build as build_feeds
from app.features.form_builder.qtside.canvas.layers.logic_badges import build as build_badges
from app.features.form_builder.qtside.canvas.layers.logic_badges import forget_badge_memo
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.unit

FORM = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QSpinBox" name="qtySpin">
     <property name="cbcsEnabledWhen"><string>totalLabel</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Qty</string></property>
     <property name="cbcsValue"><string>qtySpin</string></property>
     <property name="cbcsEnabledWhen"><string>discountCheck</string></property>
    </widget>
   </item>
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="cbcsVisibleWhen"><string>qtySpin</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="noteEdit">
     <property name="cbcsValidate"><string>[{"check": "required"}]</string></property>
    </widget>
   </item>
  </layout>
""",
)


def _world(document: object, current: object) -> tuple:
    placed = []
    x = 40
    for name in ("Form", "qtySpin", "totalLabel", "discountCheck", "noteEdit"):
        found = document.by_name(name)
        if found:
            placed.append(SimpleNamespace(node=found[0], rect=CanvasRect(x, 80, 90, 28)))
            x += 140
    static = SimpleNamespace(
        view=ViewMap(1.0, CanvasPoint(0, 0), Size(800, 600)),
        placed=tuple(placed),
        content=(),
    )
    inputs = SimpleNamespace(
        document=document,
        selection=SimpleNamespace(current=current),
        viewport=CanvasRect(0, 0, 800, 600),
        chrome=(),
        measure=lambda text: len(text) * 7,
    )
    return static, inputs


def _badges(document: object) -> dict:
    forget_badge_memo()
    current = document.by_name("totalLabel")[0]
    static, inputs = _world(document, current)
    output = build_badges(static, inputs, True)
    found = {}
    for item in output.items:
        assert isinstance(item, LayerItem)
        data = item.data
        assert isinstance(data, tuple) and data[0] == "badge"
        found[data[1]] = data
    return found


def test_rule_widgets_show_equals_and_question_badges() -> None:
    session = open_session(FORM)
    try:
        marks = _badges(session.document)
        value = marks["totalLabel"]
        assert value[3] == "="
        assert value[4] == 2
        assert marks["discountCheck"][3] == "?"
        assert marks["noteEdit"][3] == "!"
    finally:
        session.dispose()


def test_feed_arrows_follow_names_the_selection_reads_and_is_read_by() -> None:
    session = open_session(FORM)
    try:
        document = session.document
        current = document.by_name("totalLabel")[0]
        static, inputs = _world(document, current)
        selected = build_feeds(static, inputs, "selected")
        pairs = set()
        for item in selected.items:
            assert isinstance(item, LayerItem)
            data = item.data
            assert isinstance(data, tuple) and data[0] == "feed"
            pairs.add((data[1], data[2]))
        assert pairs == {("qtySpin", "totalLabel"), ("discountCheck", "totalLabel")}
        assert selected.targets == ()
        other = document.by_name("noteEdit")[0]
        _static, quiet = _world(document, other)
        assert build_feeds(static, quiet, "selected").items == ()
        every = build_feeds(static, quiet, "all")
        all_pairs = {(item.data[1], item.data[2]) for item in every.items}
        assert ("qtySpin", "discountCheck") in all_pairs
        assert ("qtySpin", "totalLabel") in all_pairs
    finally:
        session.dispose()


def test_a_stacked_widget_keeps_its_badge_off_the_selection_chip() -> None:
    """A full-width neighbour blocks every outside corner. The mark moves inside, opposite the chip."""
    session = open_session(FORM)
    try:
        document = session.document
        current = document.by_name("totalLabel")[0]
        forget_badge_memo()
        placed = []
        widths = {"qtySpin": (40, 40), "totalLabel": (40, 80), "discountCheck": (40, 220), "noteEdit": (40, 260)}
        for name, (x, y) in widths.items():
            found = document.by_name(name)
            if found:
                placed.append(SimpleNamespace(node=found[0], rect=CanvasRect(x, y, 280, 28)))
        static = SimpleNamespace(
            view=ViewMap(1.0, CanvasPoint(0, 0), Size(800, 600)),
            placed=tuple(placed),
            content=(),
        )
        inputs = SimpleNamespace(
            document=document,
            selection=SimpleNamespace(current=current, ids=(current,)),
            viewport=CanvasRect(0, 0, 800, 600),
            chrome=(),
            measure=lambda text: len(text) * 7,
            sizing=None,
            dock=None,
        )
        output = build_badges(static, inputs, True)
        mark = next(item for item in output.items if item.data[1] == "totalLabel")
        rect = next(item.rect for item in placed if item.node == current)
        assert mark.rect.x >= rect.x + rect.width / 2
    finally:
        session.dispose()


def test_feed_ink_matches_connection_arrows(qapp: QApplication) -> None:
    """Dashed feed pixels use ov.connect and clear the backdrop by the connection-arrow margin."""
    del qapp
    from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
    from app.features.form_builder.qtside.canvas.layers.feeds import paint
    from app.features.form_builder.qtside.theme.overlay import OVERLAY, BackdropPalette, CanvasPalette
    from app.qt.QtGui import QColor, QImage, QPainter

    session = open_session(FORM)
    try:
        document = session.document
        current = document.by_name("totalLabel")[0]
        static, inputs = _world(document, current)
        selected = build_feeds(static, inputs, "selected")
        item = next(row for row in selected.items if row.data[1] == "qtySpin" and row.data[2] == "totalLabel")
        assert isinstance(item, LayerItem)
        bounds = item.rect
        image = QImage(bounds.width + 8, bounds.height + 8, QImage.Format.Format_ARGB32)
        backdrop = QColor("#E9EBEF")
        image.fill(backdrop)
        painter = QPainter(image)
        painter.translate(-(bounds.x - 4), -(bounds.y - 4))
        paint(painter, item, CanvasPalette(OVERLAY, BackdropPalette("#E9EBEF", "", "", "", "", "", "", "")))
        painter.end()
        connect = QColor(OVERLAY.connect[:7])
        margin = max(
            abs(connect.red() - backdrop.red()),
            abs(connect.green() - backdrop.green()),
            abs(connect.blue() - backdrop.blue()),
        )
        hits = 0
        strongest = 0
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                gap = max(
                    abs(pixel.red() - connect.red()),
                    abs(pixel.green() - connect.green()),
                    abs(pixel.blue() - connect.blue()),
                )
                if gap > 28:
                    continue
                hits += 1
                strongest = max(
                    strongest,
                    abs(pixel.red() - backdrop.red()),
                    abs(pixel.green() - backdrop.green()),
                    abs(pixel.blue() - backdrop.blue()),
                )
        assert hits >= 20
        assert strongest >= int(margin * 0.65)
    finally:
        session.dispose()


def test_a_missing_name_draws_no_arrow_and_feeds_only_enter_the_selection() -> None:
    source = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Total</string></property>
     <property name="cbcsValue"><string>oldName * qtySpin</string></property>
    </widget>
   </item>
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="cbcsEnabledWhen"><string>totalLabel</string></property>
    </widget>
   </item>
  </layout>
""",
    )
    session = open_session(source)
    try:
        document = session.document
        current = document.by_name("totalLabel")[0]
        placed = []
        x = 40
        for name in ("Form", "qtySpin", "totalLabel", "discountCheck"):
            found = document.by_name(name)
            if found:
                placed.append(SimpleNamespace(node=found[0], rect=CanvasRect(x, 80, 90, 28)))
                x += 140
        static = SimpleNamespace(
            view=ViewMap(1.0, CanvasPoint(0, 0), Size(800, 600)),
            placed=tuple(placed),
            content=(),
        )
        inputs = SimpleNamespace(
            document=document,
            selection=SimpleNamespace(current=current),
            viewport=CanvasRect(0, 0, 800, 600),
            chrome=(),
            measure=lambda text: len(text) * 7,
        )
        selected = build_feeds(static, inputs, "selected")
        pairs = []
        for item in selected.items:
            assert isinstance(item, LayerItem)
            data = item.data
            assert isinstance(data, tuple)
            pairs.append((data[1], data[2]))
        assert pairs == [("qtySpin", "totalLabel")]
        every = {(item.data[1], item.data[2]) for item in build_feeds(static, inputs, "all").items}
        assert ("oldName", "totalLabel") not in every
        assert ("totalLabel", "discountCheck") in every
    finally:
        session.dispose()


def test_rules_without_events_still_plan_badges_in_design() -> None:
    assert layer_plan(True, "", False, False, False) == (False, None)
    assert layer_plan(True, "", False, False, False, True) == (True, None)
    assert layer_plan(True, "", True, False, False, True) == (True, "selected")
    assert layer_plan(True, "connections", False, False, False, True) == (False, "all")
    assert layer_plan(True, "tab_order", True, True, False, True) == (False, None)
