"""Page title bar and the canvas backdrop."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.session import FormSession  # noqa: E402
from app.features.form_builder.integration.canvas import FormCanvas  # noqa: E402
from app.features.form_builder.integration.content_source import form_scope  # noqa: E402
from app.features.form_builder.qtside.realize.api import Realizer  # noqa: E402
from app.qt.QtGui import QColor, QFont  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.qt.qt_compat import enum_value  # noqa: E402
from tests.unit.features.form_builder.test_workbench import _open  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="windowTitle">
   <string>Monthly invoice</string>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _near(color: QColor, hex_color: str, tolerance: int = 28) -> bool:
    target = QColor(hex_color)
    return (
        abs(color.red() - target.red()) <= tolerance
        and abs(color.green() - target.green()) <= tolerance
        and abs(color.blue() - target.blue()) <= tolerance
    )


def test_page_title_shows_the_window_title_in_the_runtime_font(qapp: QApplication, tmp_path: Path) -> None:
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    try:
        surface.resize(640, 480)
        surface.show()
        qapp.processEvents()
        title = surface.findChild(QWidget, "formBuilder.pageTitle")
        assert title is not None
        assert title.text() == "Monthly invoice"
        assert title.font().pixelSize() == 11
        expected = getattr(getattr(QFont, "Weight", QFont), "DemiBold")
        assert enum_value(title.font().weight()) == enum_value(expected)
        image = title.grab().toImage()
        assert image.width() > 80
        left = [_near(image.pixelColor(x, 11), "#3C3C3C", 36) for x in range(8, 48)]
        right = [_near(image.pixelColor(x, 11), "#6B6B6B", 24) for x in range(image.width() - 40, image.width() - 8)]
        assert any(left)
        assert any(right)
    finally:
        surface.release()
        parent.deleteLater()


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_canvas_backdrop_starts_from_backdrop_colors(monkeypatch: pytest.MonkeyPatch, qapp: QApplication, tmp_path: Path) -> None:
    del tmp_path

    def _sentinel(**_kwargs: object) -> tuple[str, str]:
        return ("#010203", "#040506")

    monkeypatch.setattr(
        "app.features.form_builder.integration.canvas.backdrop_colors",
        _sentinel,
    )
    session = FormSession.open(_FORM, path="/tmp/invoice.ui", scope=form_scope("/tmp/invoice.ui", None))
    parent = QWidget()
    canvas = FormCanvas(session, Realizer(session), _Host(), parent)
    try:
        canvas.resize(320, 240)
        canvas.show()
        qapp.processEvents()
        color = canvas.viewport().grab().toImage().pixelColor(4, 4)
        assert (color.red(), color.green(), color.blue()) == (1, 2, 3)
    finally:
        canvas.dispose()
        parent.deleteLater()
