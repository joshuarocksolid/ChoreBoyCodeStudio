# pyright: reportAttributeAccessIssue=false
"""Sizing panel, why-text, and preview. Pain P-2 and P-12."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtCore import QPoint, QPointF, Qt
from app.qt.qt_compat import wrapper_is_valid
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QGraphicsProxyWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QWidget,
)
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import opened

pytestmark = pytest.mark.usefixtures("qapp")

_COLUMN = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>180</width><height>120</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="stay"><property name="text"><string>Stay</string></property></widget>
   </item>
   <item>
    <widget class="QPushButton" name="grow"><property name="text"><string>Grow</string></property></widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>240</width><height>120</height></rect></property>
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0">
    <widget class="QPushButton" name="cell"><property name="text"><string>Cell</string></property></widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>80</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_ROW = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>80</height></rect></property>
  <layout class="QHBoxLayout" name="horizontalLayout">
   <item>
    <widget class="QLabel" name="caption"><property name="text"><string>Email address</string></property></widget>
   </item>
   <item>
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


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

    def open_context_menu(self, node: object, at: object) -> None:
        return None


def _id(session: object, name: str) -> object:
    document = session.document  # type: ignore[attr-defined]
    for widget in document.iter_widgets():
        if widget.object_name == name:
            return widget.id
    raise AssertionError(name)


def _show(session: object, realizer: object) -> Tuple[QWidget, InspectorPane]:
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)  # type: ignore[arg-type]
    pane.resize(320, 640)
    pane.show()
    return pane, pane


def _select(session: object, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[attr-defined]
    pane.flush()
    _events()


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _button(pane: QWidget, name: str) -> QToolButton:
    found = pane.findChild(QToolButton, name)
    assert isinstance(found, QToolButton), name
    return found


@pytest.mark.pain("P-2")
def test_reset_removes_minimum_size_from_the_file() -> None:
    with opened(_COLUMN) as (session, realizer):
        pane, _same = _show(session, realizer)
        _select(session, pane, "stay")
        edit = pane.findChild(QLineEdit, "formBuilder.size.minimumSize.width")
        assert isinstance(edit, QLineEdit)
        assert edit.accessibleName()
        edit.setText("80")
        edit.editingFinished.emit()
        _events()
        assert "minimumSize" in write_ui(session.document).text
        before = len(session.log.entries())
        _button(pane, "formBuilder.size.minimumSize.reset").click()
        _events()
        assert len(session.log.entries()) == before + 1
        assert "minimumSize" not in write_ui(session.document).text
        pane.dispose()


_ROW_OF_BUTTONS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>180</width><height>80</height></rect></property>
  <layout class="QHBoxLayout" name="horizontalLayout">
   <item>
    <widget class="QPushButton" name="stay"><property name="text"><string>Stay</string></property></widget>
   </item>
   <item>
    <widget class="QPushButton" name="grow"><property name="text"><string>Grow</string></property></widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.mark.pain("P-2")
def test_fill_and_stretch_let_the_second_button_grow_wider() -> None:
    with opened(_ROW_OF_BUTTONS) as (session, realizer):
        pane, _same = _show(session, realizer)
        _select(session, pane, "grow")
        _button(pane, "formBuilder.size.width.Fill").click()
        share = pane.findChild(QWidget, "formBuilder.size.share.h.value")
        assert share is not None
        share.setValue(1)  # type: ignore[attr-defined]
        share.editingFinished.emit()  # type: ignore[attr-defined]
        _events()
        assert len(session.log.entries()) == 2
        root = realizer.root_widget
        assert root is not None
        root.resize(420, 160)
        layout = root.layout()
        assert layout is not None
        layout.activate()
        _events()
        stay = root.findChild(QPushButton, "stay")
        grow = root.findChild(QPushButton, "grow")
        assert stay is not None and grow is not None
        assert grow.width() > stay.width()
        assert abs(stay.width() - stay.sizeHint().width()) <= 4
        text = write_ui(session.document).text
        assert 'name="stay"' in text
        assert "<x>" in text
        stay_block = text.split('name="stay"', 1)[1].split("</widget>", 1)[0]
        grow_block = text.split('name="grow"', 1)[1].split("</widget>", 1)[0]
        assert "<x>" not in stay_block
        assert "<y>" not in stay_block
        assert "<x>" not in grow_block
        pane.dispose()


def test_why_text_uses_the_live_widget_for_box_grid_and_form() -> None:
    cases = (
        (_COLUMN, "grow", "QVBoxLayout"),
        (_GRID, "cell", "QGridLayout"),
        (_FORM, "email", "QFormLayout"),
    )
    for xml, name, _kind in cases:
        with opened(xml) as (session, realizer):
            pane, _same = _show(session, realizer)
            _select(session, pane, name)
            label = pane.findChild(QLabel, "formBuilder.sizeWhy")
            assert isinstance(label, QLabel)
            root = realizer.root_widget
            assert root is not None
            widget = root.findChild(QWidget, name)
            assert widget is not None
            text = label.text()
            assert text.startswith("%d × %d px." % (widget.width(), widget.height()))
            assert str(widget.sizeHint().width()) in text or str(widget.width()) in text
            pane.dispose()


def test_one_sizing_change_is_one_undo_step() -> None:
    with opened(_COLUMN) as (session, realizer):
        pane, _same = _show(session, realizer)
        _select(session, pane, "grow")
        _button(pane, "formBuilder.size.width.Fill").click()
        _events()
        assert len(session.log.entries()) == 1
        assert session.log.undo_label() == "Size"
        session.log.undo()
        assert session.document.get(_id(session, "grow")).prop("sizePolicy") is None  # type: ignore[attr-defined]
        pane.dispose()


@pytest.mark.pain("P-12")
def test_point_size_preview_reflows_and_writes_no_child_geometry() -> None:
    with opened(_ROW) as (session, realizer):
        parent = QWidget()
        canvas = FormCanvas(session, realizer, _Host(), parent)
        parent.resize(640, 320)
        canvas.resize(640, 320)
        parent.show()
        _events()
        before = write_ui(session.document).text
        steps = len(session.log.entries())
        canvas.preview.set_points(10)
        _events()
        root = realizer.root_widget
        assert root is not None
        caption = root.findChild(QLabel, "caption")
        assert caption is not None
        narrow = caption.width()
        canvas.preview.set_points(16)
        _events()
        wide = caption.width()
        assert wide != narrow
        saved = write_ui(session.document).text
        assert saved == before
        assert len(session.log.entries()) == steps
        caption_block = saved.split('name="caption"', 1)[1].split("</widget>", 1)[0]
        field_block = saved.split('name="email"', 1)[1].split("</widget>", 1)[0]
        assert "<x>" not in caption_block
        assert "<y>" not in caption_block
        assert "<x>" not in field_block
        assert "<y>" not in field_block
        pill = canvas.findChild(QLabel, "formBuilder.previewPill")
        assert isinstance(pill, QLabel) and pill.isVisible()
        assert "Reset" in pill.text()
        canvas.preview.reset()
        assert not pill.isVisible()
        canvas.dispose()
        parent.deleteLater()


def test_preview_and_two_widths_do_not_dirty_the_document() -> None:
    with opened(_ROW) as (session, realizer):
        parent = QWidget()
        canvas = FormCanvas(session, realizer, _Host(), parent)
        parent.resize(900, 400)
        canvas.resize(900, 400)
        parent.show()
        _events()
        before = write_ui(session.document).text
        steps = len(session.log.entries())
        canvas.preview.set_text_factor(1.25)
        canvas.preview.set_screen(150)
        canvas.preview.toggle_widths()
        _events()
        assert write_ui(session.document).text == before
        assert len(session.log.entries()) == steps
        assert canvas.findChild(QLabel, "formBuilder.narrowChip") is not None
        assert canvas.findChild(QLineEdit, "formBuilder.wideChip") is not None
        canvas.preview.toggle_widths()
        canvas.preview.reset()
        assert write_ui(session.document).text == before
        canvas.dispose()
        parent.deleteLater()


_NARROW = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>200</height></rect></property>
  <property name="minimumSize"><size><width>300</width><height>200</height></size></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="cancel"><property name="text"><string>Cancel</string></property></widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_HEADING = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>120</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="total">
     <property name="text"><string>Total</string></property>
     <property name="font"><font><pointsize>18</pointsize><bold>true</bold></font></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="body"><property name="text"><string>Total</string></property></widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _canvas(session: FormSession, realizer: Realizer, width: int = 1100, height: int = 480) -> Tuple[QWidget, FormCanvas]:
    parent = QWidget()
    canvas = FormCanvas(session, realizer, _Host(), parent)
    parent.resize(width, height)
    canvas.resize(width, height)
    parent.show()
    _events()
    return parent, canvas


def test_fill_on_a_button_height_leaves_the_width_at_its_default() -> None:
    with opened(_COLUMN) as (session, realizer):
        pane, _same = _show(session, realizer)
        _select(session, pane, "stay")
        _button(pane, "formBuilder.size.height.Fill").click()
        _events()
        width_hug = _button(pane, "formBuilder.size.width.Hug")
        width_fill = _button(pane, "formBuilder.size.width.Fill")
        assert width_hug.property("fbOutline") == "true"
        assert not width_hug.isChecked()
        assert not width_fill.isChecked()
        note = pane.findChild(QWidget, "formBuilder.size.h").findChild(QLabel, "formBuilder.rowNote")  # type: ignore[union-attr]
        assert isinstance(note, QLabel)
        assert not note.text().startswith("Custom")
        assert _button(pane, "formBuilder.size.height.Fill").isChecked()
        pane.dispose()


def test_why_text_tracks_the_widget_after_a_text_size_preview() -> None:
    with opened(_COLUMN) as (session, realizer):
        parent, canvas = _canvas(session, realizer)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        pane.resize(320, 640)
        pane.show()
        _select(session, pane, "grow")
        label = pane.findChild(QLabel, "formBuilder.sizeWhy")
        assert isinstance(label, QLabel)
        root = realizer.root_widget
        assert root is not None
        widget = root.findChild(QPushButton, "grow")
        assert widget is not None
        canvas.preview.set_points(16)
        _events()
        assert label.text().startswith("%d × %d px." % (widget.width(), widget.height()))
        canvas.dispose()
        pane.dispose()
        parent.deleteLater()


def test_hug_with_a_maximum_explains_the_live_width() -> None:
    with opened(_ROW) as (session, realizer):
        parent, canvas = _canvas(session, realizer)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        pane.resize(320, 640)
        pane.show()
        _select(session, pane, "email")
        _button(pane, "formBuilder.size.width.Hug").click()
        edit = pane.findChild(QLineEdit, "formBuilder.size.maximumSize.width")
        assert isinstance(edit, QLineEdit)
        edit.setText("160")
        edit.editingFinished.emit()
        _events()
        root = realizer.root_widget
        assert root is not None
        root.resize(640, 160)
        layout = root.layout()
        assert layout is not None
        layout.activate()
        _events()
        widget = root.findChild(QLineEdit, "email")
        assert widget is not None
        label = pane.findChild(QLabel, "formBuilder.sizeWhy")
        assert isinstance(label, QLabel)
        text = label.text()
        assert text.startswith("%d × %d px." % (widget.width(), widget.height()))
        assert abs(int(widget.width()) - int(widget.sizeHint().width())) > 2
        assert "Width stops at its maximum of %d px." % int(widget.maximumWidth()) in text
        assert "Width is what" not in text
        canvas.dispose()
        pane.dispose()
        parent.deleteLater()


def test_a_squeezed_label_names_the_hint_floor() -> None:
    with opened(_ROW) as (session, realizer):
        parent, canvas = _canvas(session, realizer)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        pane.resize(320, 640)
        pane.show()
        _select(session, pane, "caption")
        root = realizer.root_widget
        assert root is not None
        widget = root.findChild(QLabel, "caption")
        assert widget is not None
        widget.setMaximumWidth(24)
        root.resize(80, 80)
        layout = root.layout()
        assert layout is not None
        layout.activate()
        _events()
        assert widget is not None
        assert int(widget.width()) < int(widget.sizeHint().width())
        floor = max(int(widget.minimumSize().width()), int(widget.minimumSizeHint().width()))
        label = pane.findChild(QLabel, "formBuilder.sizeWhy")
        assert isinstance(label, QLabel)
        assert label.text().startswith("%d × %d px." % (widget.width(), widget.height()))
        assert "can't go below %d px." % floor in label.text()
        assert "can't go below 0 px." not in label.text()
        canvas.dispose()
        pane.dispose()
        parent.deleteLater()


def test_a_click_in_the_wide_copy_selects_that_widget() -> None:
    with opened(_COLUMN) as (session, realizer):
        parent, canvas = _canvas(session, realizer, 1200, 520)
        canvas.preview.toggle_widths()
        _events()
        wide_root = _click_wide(canvas, "grow")
        _events()
        assert session.selection.state.current == _id(session, "grow")  # type: ignore[attr-defined]
        canvas.preview.toggle_widths()
        _events()
        assert not wrapper_is_valid(wide_root)
        canvas.dispose()
        parent.deleteLater()


def test_two_widths_uses_the_stored_minimum_and_puts_it_back() -> None:
    with opened(_NARROW) as (session, realizer):
        parent, canvas = _canvas(session, realizer, 1200, 520)
        root = realizer.root_widget
        assert root is not None
        canvas.preview.toggle_widths()
        _events()
        chip = canvas.findChild(QLabel, "formBuilder.narrowChip")
        assert isinstance(chip, QLabel)
        number = int(re.search(r"(\d+)", chip.text()).group(1))  # type: ignore[union-attr]
        assert number >= 300
        assert int(root.minimumWidth()) >= 300
        canvas.preview.toggle_widths()
        _events()
        assert root.minimumWidth() == 300
        assert root.minimumHeight() == 200
        canvas.dispose()
        parent.deleteLater()


def test_a_saved_point_size_stays_larger_than_the_preview() -> None:
    with opened(_HEADING) as (session, realizer):
        parent, canvas = _canvas(session, realizer)
        canvas.preview.set_points(10)
        _events()
        root = realizer.root_widget
        assert root is not None
        sheet = root.styleSheet()
        star = re.search(r"\* \{ font-size: ([0-9.]+)pt", sheet)
        heading = root.findChild(QLabel, "total")
        assert heading is not None
        rule = re.search(r"#total \{ font-size: ([0-9.]+)pt", heading.styleSheet())
        assert star is not None and rule is not None
        assert float(rule.group(1)) > float(star.group(1))
        body = root.findChild(QLabel, "body")
        assert heading is not None and body is not None
        assert heading.sizeHint().height() > body.sizeHint().height()
        canvas.preview.set_text_factor(1.0)
        _events()
        pill = canvas.findChild(QLabel, "formBuilder.previewPill")
        assert isinstance(pill, QLabel)
        assert not pill.isVisible()
        canvas.dispose()
        parent.deleteLater()


def _proxies(canvas: FormCanvas) -> List[QGraphicsProxyWidget]:
    scene = canvas.scene()
    assert scene is not None
    return [
        item
        for item in scene.items()
        if isinstance(item, QGraphicsProxyWidget) and item.isVisible() and item.widget() is not None
    ]


def _click_wide(canvas: FormCanvas, name: str) -> QWidget:
    proxies = _proxies(canvas)
    assert len(proxies) >= 2
    wide = max(proxies, key=lambda item: item.sceneBoundingRect().width())
    narrow = min(proxies, key=lambda item: item.sceneBoundingRect().width())
    root = wide.widget()
    assert root is not None
    target = root.findChild(QWidget, name)
    assert isinstance(target, QWidget)
    center = target.mapTo(root, QPoint(max(1, target.width() // 2), max(1, target.height() // 2)))
    scene_pos = wide.mapToScene(QPointF(float(center.x()), float(center.y())))
    assert wide.sceneBoundingRect().contains(scene_pos)
    assert not narrow.sceneBoundingRect().contains(scene_pos)
    canvas.centerOn(scene_pos)
    _events()
    view_pos = canvas.mapFromScene(scene_pos)
    QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, view_pos)
    return root


def _show_why(pane: InspectorPane) -> None:
    why = pane.findChild(QLabel, "formBuilder.sizeWhy")
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if isinstance(area, QScrollArea) and isinstance(why, QLabel):
        area.ensureWidgetVisible(why, 0, 12)


def test_sizing_screenshots(qapp) -> None:  # type: ignore[no-untyped-def]
    out = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not out:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    with opened(_COLUMN) as (session, realizer):
        host = QWidget()
        layout = QHBoxLayout(host)
        canvas = FormCanvas(session, realizer, _Host(), host)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        layout.addWidget(canvas, 1)
        layout.addWidget(pane)
        host.show()
        _select(session, pane, "stay")
        _button(pane, "formBuilder.size.height.Fill").click()
        _events()
        _grab(qapp, host, canvas, pane, folder, "button-height-fill")
        _select(session, pane, "grow")
        _button(pane, "formBuilder.size.width.Fill").click()
        _events()
        _grab(qapp, host, canvas, pane, folder, "size-fill")
        _select(session, pane, "stay")
        _button(pane, "formBuilder.size.reset").click()
        _events()
        _grab(qapp, host, canvas, pane, folder, "size-hug")
        canvas.preview.set_points(10)
        _grab(qapp, host, canvas, pane, folder, "preview-10")
        canvas.preview.set_points(16)
        _grab(qapp, host, canvas, pane, folder, "preview-16")
        canvas.preview.reset()
        canvas.preview.toggle_widths()
        _click_wide(canvas, "grow")
        _events()
        _grab(qapp, host, canvas, pane, folder, "widths")
        canvas.dispose()
        pane.dispose()
        host.close()
    with opened(_HEADING) as (session, realizer):
        host = QWidget()
        layout = QHBoxLayout(host)
        canvas = FormCanvas(session, realizer, _Host(), host)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        layout.addWidget(canvas, 1)
        layout.addWidget(pane)
        host.show()
        _select(session, pane, "total")
        canvas.preview.set_points(16)
        _events()
        _grab(qapp, host, canvas, pane, folder, "heading-16")
        canvas.dispose()
        pane.dispose()
        host.close()


def _grab(qapp, host: QWidget, canvas: FormCanvas, pane: InspectorPane, folder: Path, stem: str) -> None:  # type: ignore[no-untyped-def]
    modes = ("light", "dark") if stem != "size-fill" else ("light", "dark", "high_contrast_light", "high_contrast_dark")
    sizes = ((1080, 600), (1400, 900))
    for mode in modes:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        canvas.apply_theme(tokens)
        pane.apply_chrome(chrome_for(tokens))
        for width, height in sizes:
            if mode.startswith("high_contrast") and (width, height) != (1080, 600):
                continue
            host.resize(width, height)
            qapp.processEvents()
            if stem == "size-fill":
                _show_why(pane)
                qapp.processEvents()
            if stem == "widths":
                proxies = _proxies(canvas)
                if proxies:
                    wide = max(proxies, key=lambda item: item.sceneBoundingRect().width())
                    root = wide.widget()
                    target: Optional[QWidget] = None
                    if root is not None:
                        target = root.findChild(QWidget, "grow")
                    if target is not None and root is not None:
                        point = target.mapTo(root, QPoint(max(1, target.width() // 2), max(1, target.height() // 2)))
                        canvas.centerOn(wide.mapToScene(QPointF(float(point.x()), float(point.y()))))
                    else:
                        canvas.centerOn(wide)
                    qapp.processEvents()
            image = host.grab()
            image.save(str(folder / ("%s-%s-%dx%d.png" % (stem, mode, width, height))))
