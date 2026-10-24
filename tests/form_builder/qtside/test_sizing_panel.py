# pyright: reportAttributeAccessIssue=false
"""Sizing panel, why-text, and preview. Pain P-2 and P-12."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QWidget
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


@pytest.mark.pain("P-2")
def test_fill_and_stretch_let_the_second_button_grow_wider() -> None:
    with opened(_COLUMN) as (session, realizer):
        pane, _same = _show(session, realizer)
        _select(session, pane, "stay")
        _button(pane, "formBuilder.size.width.Hug").click()
        _select(session, pane, "grow")
        _button(pane, "formBuilder.size.width.Fill").click()
        share = pane.findChild(QWidget, "formBuilder.size.share.v.value")
        assert share is not None
        share.setValue(1)  # type: ignore[attr-defined]
        share.editingFinished.emit()  # type: ignore[attr-defined]
        _events()
        assert len(session.log.entries()) == 3
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


def test_sizing_screenshots(qapp) -> None:  # type: ignore[no-untyped-def]
    out = os.environ.get("CBCS_FB_SCREENSHOT_DIR")
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
        _select(session, pane, "grow")
        _button(pane, "formBuilder.size.width.Fill").click()
        _events()
        _grab(qapp, host, canvas, pane, folder, "size-fill")
        _select(session, pane, "stay")
        _button(pane, "formBuilder.size.width.Hug").click()
        _events()
        _grab(qapp, host, canvas, pane, folder, "size-hug")
        canvas.preview.set_points(10)
        _grab(qapp, host, canvas, pane, folder, "preview-10")
        canvas.preview.set_points(16)
        _grab(qapp, host, canvas, pane, folder, "preview-16")
        canvas.preview.reset()
        canvas.preview.toggle_widths()
        _grab(qapp, host, canvas, pane, folder, "widths")
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
            image = host.grab()
            image.save(str(folder / ("%s-%s-%dx%d.png" % (stem, mode, width, height))))
