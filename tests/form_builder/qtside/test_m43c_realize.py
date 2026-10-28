# pyright: reportAttributeAccessIssue=false
"""Canvas pictures come from the form's .qrc on disk (UX-PED-104)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import ResourcePixmap, StringValue

from app.qt.QtGui import QColor, QImage
from app.qt.QtWidgets import QLabel, QPushButton, QWidget
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


_TEXT = '<property name="text"><string%s>%s</string></property>'
_PIXMAP = '<property name="pixmap"><pixmap>dot.png</pixmap></property>'
# (name, notr, text, text first): the four orders generated code can take.
_LABELS = (
    ("trFirst", "", "Hello", True),
    ("trAfter", "", "Hello", False),
    ("notrFirst", ' notr="true"', "Hello", True),
    ("notrAfter", ' notr="true"', "Hello", False),
    ("emptyFirst", "", "", True),
)


def _labels_form() -> str:
    widgets = []
    for name, notr, text, text_first in _LABELS:
        text_xml = _TEXT % (notr, text)
        pair = (text_xml, _PIXMAP) if text_first else (_PIXMAP, text_xml)
        widgets.append('  <widget class="QLabel" name="%s">\n   %s\n   %s\n  </widget>' % ((name,) + pair))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n%s\n </widget>\n</ui>\n' % "\n".join(widgets)
    )


def _shown(label: QLabel) -> Tuple[str, bool]:
    return label.text(), not label.pixmap().isNull()


def _generated(text: str, folder: Path) -> Dict[str, Tuple[str, bool]]:
    forms = folder / "forms"
    forms.mkdir()
    path = forms / "labels.ui"
    path.write_text(text, encoding="utf-8")
    scope = FormScope(kind="project", ui_path=str(path), project_root=str(folder), generated_path=str(forms / "ui_labels.py"))
    document = read_ui(text, allocator=IdAllocator()).document
    code = generate_form_module(document, scope=scope, source_bytes=text.encode("utf-8")).text
    assert code
    namespace: Dict[str, object] = {}
    exec(compile(code, "ui_labels.py", "exec"), namespace)
    ui_cls = next(value for value in namespace.values() if isinstance(value, type) and hasattr(value, "setupUi"))
    host = QWidget()
    ui = ui_cls()
    ui.setupUi(host)  # type: ignore[attr-defined]
    return {name: _shown(getattr(ui, name)) for name, _notr, _text, _first in _LABELS}


def test_a_label_with_text_and_a_picture_looks_as_the_generated_code_shows_it(
    tmp_path: Path, qapp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QLabel text and pixmap clear each other; retranslateUi sets translatable text last."""
    del qapp
    _png(tmp_path / "dot.png")
    monkeypatch.chdir(tmp_path)
    text = _labels_form()
    expected = _generated(text, tmp_path)
    assert expected["trFirst"] == ("Hello", False)
    assert expected["notrFirst"] == ("", True)
    session, realizer = realize(text, str(tmp_path / "labels.ui"))
    try:
        ids = {name: session.document.by_name(name)[0] for name, _n, _t, _f in _LABELS}
        canvas = {name: _shown(realizer.widget_for(node))  # type: ignore[arg-type]
                  for name, node in ids.items()}
        assert canvas == expected
        # A later edit of either property ends on what the app would show.
        session.log.execute(SetProperty(ids["trAfter"], "pixmap", ResourcePixmap("dot.png")))
        session.log.execute(SetProperty(ids["notrFirst"], "text", StringValue("Bye", notr=True)))
        session.log.execute(SetProperty(ids["emptyFirst"], "text", StringValue("Now")))
        assert _shown(realizer.widget_for(ids["trAfter"])) == ("Hello", False)  # type: ignore[arg-type]
        assert _shown(realizer.widget_for(ids["notrFirst"])) == ("", True)  # type: ignore[arg-type]
        assert _shown(realizer.widget_for(ids["emptyFirst"])) == ("Now", False)  # type: ignore[arg-type]
        session.log.undo()
        assert _shown(realizer.widget_for(ids["emptyFirst"])) == ("", True)  # type: ignore[arg-type]
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
