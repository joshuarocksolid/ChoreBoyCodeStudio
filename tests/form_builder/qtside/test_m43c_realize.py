# pyright: reportAttributeAccessIssue=false
"""Canvas pictures come from the form's .qrc on disk (UX-PED-104)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtGui import QColor, QImage
from app.qt.QtWidgets import QLabel, QPushButton
from tests.form_builder.qtside.support import realize

pytestmark = pytest.mark.unit


def _png(path: Path) -> None:
    image = QImage(8, 8, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
    image.fill(QColor(220, 30, 30))
    assert image.save(str(path), "PNG")


def _form(folder: Path, *, icon: str, write_icon: bool) -> str:
    _png(folder / "save.png")
    if write_icon:
        _png(folder / "dot.png")
    (folder / "app.qrc").write_text(
        """<RCC version="1.0"><qresource prefix="/icons">
 <file>save.png</file>
 <file>dot.png</file>
</qresource></RCC>
""",
        encoding="utf-8",
    )
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>Save</string></property>
     <property name="icon"><iconset><normaloff>%s</normaloff></iconset></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="photo">
     <property name="pixmap"><pixmap>:/icons/save.png</pixmap></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources><include location="app.qrc"/></resources>
 <connections/>
</ui>
""" % icon


def test_a_button_shows_the_icon_from_the_qrc_on_disk(tmp_path: Path, qapp) -> None:
    del qapp
    text = _form(tmp_path, icon=":/icons/save.png", write_icon=True)
    session, realizer = realize(text, str(tmp_path / "form.ui"))
    try:
        button_id = session.document.by_name("ok")[0]
        button = realizer.widget_for(button_id)
        assert isinstance(button, QPushButton)
        assert button is not None and button.icon().pixmap(16, 16).isNull() is False
        assert realizer.refused(button_id, "icon") is None
        label = realizer.widget_for(session.document.by_name("photo")[0])
        assert isinstance(label, QLabel)
        pixmap = None if label is None else label.pixmap()
        assert pixmap is not None and pixmap.isNull() is False
    finally:
        realizer.dispose()
        session.dispose()


def test_a_label_keeps_its_pixmap_when_it_also_has_text(tmp_path: Path, qapp) -> None:
    del qapp
    text = _form(tmp_path, icon=":/icons/save.png", write_icon=True)
    text = text.replace(
        '<property name="pixmap"><pixmap>:/icons/save.png</pixmap></property>',
        '<property name="text"><string>Photo</string></property>\n'
        '     <property name="pixmap"><pixmap>:/icons/save.png</pixmap></property>',
    )
    session, realizer = realize(text, str(tmp_path / "form.ui"))
    try:
        label = realizer.widget_for(session.document.by_name("photo")[0])
        assert isinstance(label, QLabel)
        pixmap = None if label is None else label.pixmap()
        assert pixmap is not None and pixmap.isNull() is False
    finally:
        realizer.dispose()
        session.dispose()


def test_a_missing_picture_draws_empty_and_is_refused(tmp_path: Path, qapp) -> None:
    del qapp
    text = _form(tmp_path, icon=":/icons/dot.png", write_icon=False)
    session, realizer = realize(text, str(tmp_path / "form.ui"))
    try:
        button_id = session.document.by_name("ok")[0]
        button = realizer.widget_for(button_id)
        assert isinstance(button, QPushButton)
        assert button is not None
        assert button.icon().isNull() or button.icon().pixmap(16, 16).isNull()
        assert realizer.refused(button_id, "icon") == "Code Studio can't find :/icons/dot.png."
    finally:
        realizer.dispose()
        session.dispose()
