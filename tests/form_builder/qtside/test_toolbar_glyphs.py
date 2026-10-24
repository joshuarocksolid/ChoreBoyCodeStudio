"""Toolbar and rail controls show painted glyphs and keep their tooltips."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QIcon
from app.qt.QtWidgets import QApplication, QLabel, QToolButton, QWidget
from app.features.form_builder.integration.workbench import FormToolbar
from tests.form_builder.qtside.support import form
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)


def test_toolbar_and_rails_show_glyphs_and_keep_tooltips(tmp_path: Path, qapp: QApplication) -> None:
    parent = QWidget()
    parent.resize(1400, 800)
    surface = _open(parent, _UI, tmp_path / "form.ui")
    surface.resize(1400, 800)
    parent.show()
    qapp.processEvents()
    try:
        undo = _button(surface, "formBuilder.undo")
        assert undo.text() == ""
        assert undo.accessibleName() == "Undo"
        assert undo.toolTip().startswith("Undo")
        assert not undo.icon().isNull()
        _assert_crisp(undo)
        assert _signature(undo.icon(), "Normal") != _signature(undo.icon(), "Disabled")

        redo = _button(surface, "formBuilder.redo")
        assert redo.text() == ""
        assert redo.accessibleName() == "Redo"
        assert not redo.icon().isNull()

        zoom_out = _button(surface, "formBuilder.zoomOut")
        zoom_in = _button(surface, "formBuilder.zoomIn")
        zoom_label = _button(surface, "formBuilder.zoomLabel")
        assert zoom_out.text() == "" and zoom_out.toolTip() == "Zoom out" and not zoom_out.icon().isNull()
        assert zoom_in.text() == "" and zoom_in.toolTip() == "Zoom in" and not zoom_in.icon().isNull()
        assert "%" in zoom_label.text()
        assert zoom_label.icon().isNull()

        design = _button(surface, "formBuilder.design")
        xml = _button(surface, "formBuilder.viewXml")
        assert design.text() == "Design" and design.icon().isNull()
        assert xml.text() == "XML" and xml.icon().isNull()

        tab_order = _button(surface, "formBuilder.tabOrder")
        buddies = _button(surface, "formBuilder.buddies")
        assert tab_order.text() == "Tab order"
        assert buddies.text() == "Buddies"
        assert not tab_order.icon().isNull() and not buddies.icon().isNull()
        assert tab_order.toolButtonStyle() == _style("ToolButtonTextBesideIcon")

        preview = _button(surface, "formBuilder.preview")
        overflow = _button(surface, "formBuilder.overflow")
        assert preview.text() == "" and not preview.icon().isNull()
        assert overflow.text() == "" and overflow.toolTip() == "More" and not overflow.icon().isNull()
        assert overflow.accessibleName() == "More"

        toolbar = surface.findChild(FormToolbar, "formBuilder.toolbar")
        assert toolbar is not None
        toolbar.set_compact(True)
        assert tab_order.text() == ""
        assert buddies.text() == ""
        assert tab_order.toolButtonStyle() == _style("ToolButtonIconOnly")
        assert not tab_order.icon().isNull()

        for name, tip in (
            ("formBuilder.leftRail.outline", "Outline"),
            ("formBuilder.leftRail.insert", "Insert"),
            ("formBuilder.rightRail.properties", "Properties"),
            ("formBuilder.rightRail.behavior", "Behavior"),
        ):
            button = _button(surface, name)
            assert button.text() == ""
            assert button.toolTip() == tip
            assert button.accessibleName() == tip
            assert not button.icon().isNull()
            captions = button.findChildren(QLabel, "formBuilder.railLabel")
            assert captions
            assert all(not caption.isVisible() for caption in captions)

        pin = _button(surface, "formBuilder.pin")
        assert pin.text() == ""
        assert pin.toolTip() == "Keep this pane open"
        assert not pin.icon().isNull()
    finally:
        surface.release()
        parent.deleteLater()
        qapp.processEvents()


def _button(surface: QWidget, name: str) -> QToolButton:
    button = surface.findChild(QToolButton, name)
    assert button is not None
    return button


def _style(name: str) -> object:
    return getattr(getattr(Qt, "ToolButtonStyle", Qt), name)


def _mode(name: str) -> object:
    return getattr(getattr(QIcon, "Mode", QIcon), name)


def _assert_crisp(button: QToolButton) -> None:
    pixmap = button.icon().pixmap(QSize(16, 16))
    ratio = float(pixmap.devicePixelRatio())
    assert ratio > 0
    assert pixmap.width() == int(round(16 * ratio))
    assert pixmap.height() == int(round(16 * ratio))


def _signature(icon: QIcon, mode: str) -> int:
    pixmap = icon.pixmap(QSize(16, 16), _mode(mode))  # type: ignore[arg-type]
    image = pixmap.toImage()
    total = 0
    for y in range(image.height()):
        for x in range(image.width()):
            total += int(image.pixel(x, y))
    return total
