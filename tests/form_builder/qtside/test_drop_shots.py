# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.qt.QtCore import QPoint, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QLabel, QVBoxLayout, QWidget
from app.features.form_builder.engine.query.drop_target import DropPayload
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.workbench import OutlinePane
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.canvas.core.gesture import PlaceAsked, PlaceDrop
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form
from tests.form_builder.qtside.test_drop import (
    Stroke,
    _drag_widget_to,
    _flush,
    _mods,
    _mouse,
    _port,
    _press_move,
    _release,
    _shown,
    _widget,
)

pytestmark = pytest.mark.usefixtures("qapp")

_SIZES = ((1080, 600), (1400, 900))
_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")


@pytest.mark.timeout(120)
def test_drop_screenshots(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    scenes = (
        ("vertical", _vertical(), _vertical_point, "Insert"),
        ("grid-edge", _grid(), _grid_point, "column"),
        ("invalid", _spacer_form(), _label_point, "can't"),
    )
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        for width, height in _SIZES:
            for name, text, point_of, needle in scenes:
                _grab_drag(qapp, tokens, out, name, text, point_of, needle, width, height, mode)
            _grab_form_editor(qapp, tokens, out, width, height, mode)
            _grab_span(qapp, tokens, out, width, height, mode)
            _grab_plus(qapp, tokens, out, width, height, mode)
            _grab_outline(qapp, tokens, out, width, height, mode)


def _grab_drag(qapp, tokens, out: Path, name: str, text: str, point_of, needle: str, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(text) as (session, canvas, host):
        del session
        shell = _shell(canvas, width, height)
        canvas.apply_theme(tokens)
        _paint_status(shell, tokens, "")
        qapp.processEvents()
        end = point_of(canvas)
        source = "gap" if name == "invalid" else _source(name)
        if name == "invalid":
            _press_spacer(canvas, end)
        else:
            _press_move(canvas, source, end)
        sentence = next((item for item in reversed(host.sentences) if item), "")
        assert needle.lower() in sentence.lower(), sentence
        if name == "invalid":
            assert any(isinstance(item, Stroke) and item.role == "problem" for item in canvas.overlay().items)
        if name == "vertical":
            assert any(isinstance(item, Chip) and item.text for item in canvas.overlay().items)
        _paint_status(shell, tokens, sentence)
        qapp.processEvents()
        image = shell.grab()
        image.save(str(out / ("drop-%s-%s-%dx%d.png" % (name, mode, width, height))), "PNG")
        _release(canvas, end)
        shell.deleteLater()


def _grab_form_editor(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(_form()) as (session, canvas, _host):
        shell = _shell(canvas, width, height)
        canvas.apply_theme(tokens)
        email = _widget(canvas, "email")
        below = email.mapTo(canvas.page_widget(), QPoint(email.width() // 2, email.height() + 36))
        _drag_widget_to(canvas, "go", below)
        edits = [edit for edit in canvas.viewport().findChildren(type(email)) if edit.isVisible() and edit.text() == "New field:"]
        assert edits
        _paint_status(shell, tokens, "Drop. New field:")
        qapp.processEvents()
        image = shell.grab()
        image.save(str(out / ("drop-form-editor-%s-%dx%d.png" % (mode, width, height))), "PNG")
        shell.deleteLater()


def _shell(canvas: QWidget, width: int, height: int) -> QWidget:
    parent = canvas.parentWidget()
    assert parent is not None
    parent.resize(width, height)
    canvas.resize(width, height - 32)
    bar = QLabel(parent)
    bar.setObjectName("formBuilder.shotStatus")
    bar.setFixedHeight(32)
    layout = parent.layout()
    if layout is None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(canvas, 1)
        layout.addWidget(bar)
    return parent


def _paint_status(shell: QWidget, tokens: object, sentence: str) -> None:
    bar = shell.findChild(QLabel, "formBuilder.shotStatus")
    assert bar is not None
    bar.setText(sentence)
    bar.setStyleSheet(
        "color: %s; background: %s; border-top: 1px solid %s; padding-left: 8px;"
        % (tokens.text_primary, tokens.panel_bg, tokens.border)  # type: ignore[attr-defined]
    )


def _grab_span(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(_span()) as (session, canvas, host):
        del session
        shell = _shell(canvas, width, height)
        canvas.apply_theme(tokens)
        left = _widget(canvas, "left")
        end = left.mapTo(canvas.page_widget(), QPoint(left.width() // 2, left.height() + 8))
        _press_move(canvas, "banner", end)
        assert any(isinstance(item, Chip) and item.text for item in canvas.overlay().items)
        sentence = next((item for item in reversed(host.sentences) if item), "")
        _paint_status(shell, tokens, sentence or "Move banner")
        qapp.processEvents()
        shell.grab().save(str(out / ("drop-span-%s-%dx%d.png" % (mode, width, height))), "PNG")
        _release(canvas, end)
        shell.deleteLater()


def _grab_plus(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(_tabs()) as (session, canvas, _host):
        shell = _shell(canvas, width, height)
        canvas.apply_theme(tokens)
        tabs = session.document.by_name("tabs")[0]
        session.selection.set((tabs,), current=tabs, source=SelectionSource.PROGRAM)
        _flush()
        assert any(isinstance(item, Chip) and item.text == "+" for item in canvas.overlay().items)
        _paint_status(shell, tokens, "Add a tab")
        qapp.processEvents()
        shell.grab().save(str(out / ("drop-plus-%s-%dx%d.png" % (mode, width, height))), "PNG")
        shell.deleteLater()


def _grab_outline(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(_vertical()) as (session, canvas, _host):
        shell = _shell(canvas, width, height)
        canvas.apply_theme(tokens)
        pane = OutlinePane(lambda _node: None, lambda _collapsed: None, shell)
        pane.set_drop_color(tokens.accent)
        pane.rebuild(session.document, None)
        pane.set_drop_bridge(canvas.send, canvas.place_payload)  # type: ignore[arg-type]
        pane.setGeometry(0, 0, 220, height - 32)
        pane.show()
        receipts = session.document.by_name("receipts")[0]
        canvas.send(PlaceAsked(CanvasPoint(20, 20), DropPayload("widget", (receipts,)), ""))
        _flush()
        receipts_item = None
        role = int(getattr(Qt, "UserRole"))

        def _walk(item):  # type: ignore[no-untyped-def]
            nonlocal receipts_item
            if item.data(0, role) == int(receipts):
                receipts_item = item
            for index in range(item.childCount()):
                _walk(item.child(index))

        for index in range(pane.tree.topLevelItemCount()):
            _walk(pane.tree.topLevelItem(index))
        assert receipts_item is not None
        visual = pane.tree.visualItemRect(receipts_item)
        pane._post_target(visual.center(), False)  # type: ignore[attr-defined]
        _flush()
        assert pane._drop_line.isVisible()  # type: ignore[attr-defined]
        _paint_status(shell, tokens, "Outline drop")
        qapp.processEvents()
        shell.grab().save(str(out / ("drop-outline-%s-%dx%d.png" % (mode, width, height))), "PNG")
        canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
        shell.deleteLater()


def _span() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0" colspan="2"><widget class="QLabel" name="banner"><property name="text"><string>Banner</string></property></widget></item>
   <item row="1" column="0"><widget class="QPushButton" name="left"><property name="text"><string>Left</string></property></widget></item>
   <item row="1" column="1"><widget class="QPushButton" name="right"><property name="text"><string>Right</string></property></widget></item>
  </layout>
""",
    )


def _tabs() -> str:
    return form(
        'class="QTabWidget" name="tabs"',
        """
  <widget class="QWidget" name="pageOne"><attribute name="title"><string>One</string></attribute>
   <layout class="QVBoxLayout" name="verticalLayout"/>
  </widget>
""",
    )


def _source(name: str) -> str:
    return {"vertical": "receipts", "grid-edge": "right"}.get(name, "extra")


def _vertical() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="receipts"><property name="text"><string>Receipts</string></property></widget></item>
  </layout>
""",
    )


def _grid() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QPushButton" name="left"><property name="text"><string>Left</string></property></widget></item>
   <item row="0" column="1"><widget class="QPushButton" name="right"><property name="text"><string>Right</string></property></widget></item>
  </layout>
""",
    )


def _form() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
   <item row="1" column="1"><widget class="QPushButton" name="go"><property name="text"><string>Go</string></property></widget></item>
  </layout>
""",
    )


def _spacer_form() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <layout class="QFormLayout" name="formLayout">
     <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
     <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
    </layout>
   </item>
   <item>
    <spacer name="gap">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>80</height></size></property>
    </spacer>
   </item>
  </layout>
""",
    )


def _vertical_point(canvas):  # type: ignore[no-untyped-def]
    shop = _widget(canvas, "shop")
    return shop.mapTo(canvas.page_widget(), QPoint(shop.width() // 2, 4))


def _grid_point(canvas):  # type: ignore[no-untyped-def]
    left = _widget(canvas, "left")
    return left.mapTo(canvas.page_widget(), QPoint(2, left.height() // 2))


def _label_point(canvas):  # type: ignore[no-untyped-def]
    label = _widget(canvas, "emailLabel")
    return label.mapTo(canvas.page_widget(), label.rect().center())


def _press_spacer(canvas, end) -> None:  # type: ignore[no-untyped-def]
    root = canvas.page_widget()
    outer = root.layout()
    spacer = outer.itemAt(1).spacerItem()
    geom = spacer.geometry()
    start = QPoint(geom.x() + max(geom.width() // 2, 1), geom.y() + max(geom.height() // 2, 1))
    viewport = canvas.viewport()
    QTest.mousePress(viewport, _mouse("LeftButton"), _mods("NoModifier"), _port(canvas, root, start))
    QTest.mouseMove(viewport, _port(canvas, root, end))
    _flush()
