# pyright: reportAttributeAccessIssue=false
"""Picture, icon and picture-brush editors (UX-PED-100 … 103)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.editors._picture_picker import PicturePicker
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import QBuffer, QIODevice, Qt
from app.qt.QtGui import QColor, QFontMetrics, QImage
from app.qt.QtTest import QTest
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.engine.codegen.uic_compare import compare
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)
_UIC = "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
_NO_RESOURCE = (
    "This form uses no resource file yet. Pictures from files may be missing when the app is packaged."
)
_FILE_WARNING = "Loaded from a file path. A packaged app may not find it."


def _png_bytes() -> bytes:
    image = QImage(8, 8, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
    image.fill(QColor(20, 120, 200))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


def _seed(folder: Path, names: tuple) -> None:
    payload = _png_bytes()
    lines = []
    for name in names:
        if name != "gone.png":
            (folder / name).write_bytes(payload)
        lines.append(" <file>%s</file>" % name)
    (folder / "app.qrc").write_text(
        '<RCC version="1.0"><qresource prefix="/icons">\n%s\n</qresource></RCC>\n' % "\n".join(lines),
        encoding="utf-8",
    )


def _form(photo: str = "", icon: str = "", brush: str = "", resources: bool = True) -> str:
    photo_prop = ""
    if photo:
        photo_prop = '<property name="pixmap"><pixmap>%s</pixmap></property>' % photo
    icon_prop = ""
    if icon:
        icon_prop = "<property name=\"icon\"><iconset>%s</iconset></property>" % icon
    brush_prop = ""
    if brush:
        brush_prop = '<property name="brush">%s</property>' % brush
    resources_xml = '<resources><include location="app.qrc"/></resources>' if resources else "<resources/>"
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="photo">
     %s
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>Save</string></property>
     %s
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="title">
     <property name="text"><string>Title</string></property>
     %s
    </widget>
   </item>
  </layout>
 </widget>
 %s
 <connections/>
</ui>
""" % (photo_prop, icon_prop, brush_prop, resources_xml)


def _pane(qapp: QApplication, text: str, path: str, width: int = 1400, chrome=None):
    session, realizer = realize(text, path)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(chrome or _CHROME)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.resize(width, 900)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.set_group_expanded(GroupId.ALL, True)
    pane.flush()
    return window, pane, session, realizer


def _close(window, pane, realizer, session, qapp: QApplication) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
    qapp.processEvents()


def _select(session, name: str) -> None:
    session.selection.set((session.document.by_name(name)[0],), source=SelectionSource.PROGRAM)


def _open_row(pane: QWidget, name: str, qapp: QApplication) -> QPushButton:
    row = pane.findChild(QWidget, name)
    assert row is not None, name
    summary = row.findChild(QPushButton, "formBuilder.summary")
    assert summary is not None
    summary.click()
    qapp.processEvents()
    return summary


def _search(qapp: QApplication) -> QLineEdit:
    qapp.processEvents()
    found = [
        widget
        for widget in QApplication.allWidgets()
        if widget.objectName() == "formBuilder.pictureSearch" and widget.isVisible()
    ]
    assert found, "picture search"
    search = found[-1]
    assert isinstance(search, QLineEdit)
    return search


def _press(widget: QWidget, key: object) -> None:
    QTest.keyClick(widget, key)  # type: ignore[arg-type]
    QApplication.processEvents()


def _fit_row(qapp: QApplication, window: QWidget, pane: QWidget, row_target: int) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert scroll is not None
    width = row_target + 80
    for _ in range(40):
        window.resize(width, 900)
        pane.setFixedWidth(width)
        qapp.processEvents()
        row = scroll.viewport().width() - 16
        if row == row_target:
            return
        width += row_target - row


@pytest.mark.parity("R3-164")
def test_pixmap_from_a_resource_round_trips(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, ("save.png", "dot.png"))
    path = str(tmp_path / "picture_form.ui")
    window, pane, session, realizer = _pane(qapp, _form(), path)
    try:
        _select(session, "photo")
        pane.flush()
        before = len(session.log.entries())
        summary = _open_row(pane, "formBuilder.row.pixmap", qapp)
        popover = summary.window().findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None and popover.isVisible()
        assert popover.width() == 320
        search = _search(qapp)
        QTest.keyClicks(search, "save")
        qapp.processEvents()
        _press(search, Qt.Key.Key_Down)
        grid = search.parent().findChild(QWidget, "formBuilder.pictureGrid")
        assert grid is not None and grid.hasFocus()
        _press(grid, Qt.Key.Key_Return)
        qapp.processEvents()
        assert len(session.log.entries()) == before + 1
        assert ":/icons/save.png" in session.text()
        (tmp_path / "picture_form.ui").write_text(session.text(), encoding="utf-8")
    finally:
        _close(window, pane, realizer, session, qapp)
    reopened, again = realize((tmp_path / "picture_form.ui").read_text(encoding="utf-8"), path)
    try:
        label = again.widget_for(reopened.document.by_name("photo")[0])
        assert isinstance(label, QLabel)
        pixmap = None if label is None else label.pixmap()
        assert pixmap is not None and pixmap.isNull() is False
        loaded = QUiLoader().load(str(tmp_path / "picture_form.ui"))
        assert loaded is not None
        photo = loaded.findChild(QLabel, "photo")
        assert photo is not None and photo.pixmap() is not None and photo.pixmap().isNull() is False
        loaded.deleteLater()
    finally:
        again.dispose()
        reopened.dispose()
    if os.path.isfile(_UIC):
        monkeypatch.setenv("CBCS_FB_UIC", _UIC)
        status, interesting, count, _total = compare(tmp_path / "picture_form.ui")
        assert status == "ok", (interesting, count)


def test_pixmap_from_a_file_warns_and_esc_reverts(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("save.png",))
    outside = tmp_path / "side.png"
    outside.write_bytes(_png_bytes())
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(qapp, _form(), path)
    try:
        _select(session, "photo")
        pane.flush()
        original = session.text()
        steps = len(session.log.entries())
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        search = _search(qapp)
        QTest.keyClicks(search, "nope")
        _press(search, Qt.Key.Key_Escape)
        assert session.text() == original
        assert len(session.log.entries()) == steps
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        search = _search(qapp)
        picker = search.parent()
        assert isinstance(picker, PicturePicker)
        stored = picker.choose(str(outside))
        qapp.processEvents()
        assert stored == "side.png"
        warning = pane.findChild(QLabel, "formBuilder.pictureWarning")
        assert warning is not None and warning.isVisible()
        assert warning.text() == _FILE_WARNING
        done = _search(qapp).window().findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        assert "<pixmap>side.png</pixmap>" in session.text()
        assert len(session.log.entries()) == steps + 1
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_missing_pixmap_row_uses_the_error_colour(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("gone.png",))
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(qapp, _form(photo=":/icons/gone.png"), path)
    try:
        _select(session, "photo")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.pixmap")
        assert row is not None
        summary = row.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        assert summary.summary == "gone.png (missing)"
        assert " (" not in summary.accessibleName()
        assert summary.toolTip() == "Code Studio can't find :/icons/gone.png."
        assert summary.property("fbIssue") == "missing"
        content = pane.findChild(QWidget, "formBuilder.inspectorContent")
        assert content is not None and "#b00020" in content.styleSheet()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_no_resource_caption(qapp: QApplication, tmp_path: Path) -> None:
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(qapp, _form(resources=False), path)
    try:
        _select(session, "photo")
        pane.flush()
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        captions = [
            widget
            for widget in QApplication.allWidgets()
            if widget.objectName() == "formBuilder.pictureNoResource" and widget.isVisible()
        ]
        assert len(captions) == 1 and isinstance(captions[0], QLabel)
        assert captions[0].text() == _NO_RESOURCE
        # Nothing to search: focus starts on the one thing that works.
        focused = QApplication.focusWidget()
        assert focused is not None and focused.objectName() == "formBuilder.pictureFromFile"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_summaries_fit_the_132_px_column_at_236(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("save.png",))
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(qapp, _form(photo=":/icons/save.png"), path, width=320)
    try:
        _select(session, "photo")
        pane.flush()
        _fit_row(qapp, window, pane, 236)
        scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        assert scroll.horizontalScrollBar().maximum() == 0
        row = pane.findChild(QWidget, "formBuilder.row.pixmap")
        assert row is not None
        summary = row.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        assert summary.width() <= 132
        metrics = QFontMetrics(summary.font())
        for text in ("None", "save.png", "Mixed", "document-save"):
            assert metrics.horizontalAdvance(text + " \u25be") <= 132
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-165")
def test_icon_states_theme_and_legacy_resource_round_trip(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, ("save.png", "dot.png"))
    icon = '<normaloff>:/icons/save.png</normaloff>'
    text = _form(icon=icon).replace(
        "<iconset>",
        '<iconset resource="legacy.qrc">',
        1,
    )
    path = str(tmp_path / "icon_form.ui")
    window, pane, session, realizer = _pane(qapp, text, path)
    try:
        _select(session, "ok")
        pane.flush()
        original_resource = 'resource="legacy.qrc"'
        assert original_resource in session.text()
        _open_row(pane, "formBuilder.row.icon", qapp)
        search = _search(qapp)
        QTest.keyClicks(search, "dot")
        qapp.processEvents()
        _press(search, Qt.Key.Key_Down)
        grid = search.parent().findChild(QWidget, "formBuilder.pictureGrid")
        assert grid is not None
        _press(grid, Qt.Key.Key_Return)
        qapp.processEvents()
        _open_row(pane, "formBuilder.row.icon", qapp)
        other = _search(qapp).window().findChild(QToolButton, "formBuilder.iconOtherStates")
        assert other is not None
        other.click()
        qapp.processEvents()
        disabled = _search(qapp).window().findChild(QToolButton, "formBuilder.iconState.disabledoff")
        assert disabled is not None
        disabled.click()
        qapp.processEvents()
        search = _search(qapp)
        search.clear()
        QTest.keyClicks(search, "save")
        qapp.processEvents()
        grid = search.parent().findChild(QWidget, "formBuilder.pictureGrid")
        assert grid is not None
        _press(grid, Qt.Key.Key_Return)
        qapp.processEvents()
        theme = QApplication.focusWidget()
        # The theme field is still in the closed popover's last window. Re-open to type it.
        if not isinstance(theme, QLineEdit) or theme.objectName() != "formBuilder.iconTheme":
            _open_row(pane, "formBuilder.row.icon", qapp)
            theme = _search(qapp).window().findChild(QLineEdit, "formBuilder.iconTheme")
        assert isinstance(theme, QLineEdit)
        theme.setFocus()
        theme.clear()
        QTest.keyClicks(theme, "document-save")
        qapp.processEvents()
        done = theme.window().findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        saved = session.text()
        assert 'resource="legacy.qrc"' in saved
        assert "<normaloff>:/icons/dot.png</normaloff>" in saved
        assert "<disabledoff>:/icons/save.png</disabledoff>" in saved
        assert 'theme="document-save"' in saved
        assert len(session.log.entries()) >= 1
        (tmp_path / "icon_form.ui").write_text(saved, encoding="utf-8")
    finally:
        _close(window, pane, realizer, session, qapp)
    if os.path.isfile(_UIC):
        monkeypatch.setenv("CBCS_FB_UIC", _UIC)
        status, interesting, count, _total = compare(tmp_path / "icon_form.ui")
        assert status == "ok", (interesting, count)


def test_brush_picture_style_writes_a_texture(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("save.png",))
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(
        qapp,
        _form(brush='<brush brushstyle="SolidPattern"><color><red>0</red><green>0</green><blue>0</blue></color></brush>'),
        path,
    )
    try:
        _select(session, "title")
        pane.flush()
        before = len(session.log.entries())
        _open_row(pane, "formBuilder.row.brush", qapp)
        picture = next(
            button
            for button in QApplication.allWidgets()
            if isinstance(button, QToolButton) and button.text() == "Picture" and button.isVisible()
        )
        picture.click()
        qapp.processEvents()
        search = _search(qapp)
        QTest.keyClicks(search, "save")
        qapp.processEvents()
        _press(search, Qt.Key.Key_Return)
        qapp.processEvents()
        done = search.window().findChild(QWidget, "formBuilder.popoverDone")
        if done is not None and done.isVisible():
            done.click()
            qapp.processEvents()
        saved = session.text()
        assert 'brushstyle="TexturePattern"' in saved
        assert "<pixmap>:/icons/save.png</pixmap>" in saved
        assert len(session.log.entries()) == before + 1
    finally:
        _close(window, pane, realizer, session, qapp)


def test_picker_open_with_300_pictures_stays_under_50ms_cpu(qapp: QApplication, tmp_path: Path) -> None:
    names = tuple("p%03d.png" % index for index in range(300))
    _seed(tmp_path, names)
    text = _form()
    document = read_ui(text, allocator=IdAllocator()).document
    ui_path = str(tmp_path / "form.ui")

    class _Session:
        def __init__(self) -> None:
            self.path = ui_path
            self.document = document

    class _Services:
        def __init__(self, session: _Session) -> None:
            self.session = session

    class _Host:
        chrome = _CHROME
        label = "Pixmap"

        def __init__(self, row: QWidget) -> None:
            self.row_widget = row

        def document(self):
            return document

    row = QWidget()
    row._services = _Services(_Session())  # type: ignore[attr-defined]
    host = _Host(row)
    samples = []
    picker = None
    for _ in range(3):
        started = time.process_time()
        picker = PicturePicker(row, host, lambda _path: None)  # type: ignore[arg-type]
        picker.show()
        qapp.processEvents()
        samples.append(time.process_time() - started)
        picker.hide()
    best = min(samples)
    print("picker-300-cpu", "%.4f" % best, ["%.4f" % item for item in samples])
    assert best <= 0.050, samples
    if picker is not None:
        picker.deleteLater()
    row.deleteLater()
    qapp.processEvents()


def test_the_pixmap_row_says_when_the_label_text_hides_the_picture(qapp: QApplication, tmp_path: Path) -> None:
    """The canvas shows the text, as the app will; the row says why the picture is not seen."""
    _seed(tmp_path, ("save.png",))
    text = _form(photo=":/icons/save.png").replace(
        '<widget class="QLabel" name="photo">',
        '<widget class="QLabel" name="photo">\n     <property name="text"><string>Photo</string></property>',
    )
    window, pane, session, realizer = _pane(qapp, text, str(tmp_path / "form.ui"))
    try:
        _select(session, "photo")
        pane.flush()
        warning = pane.findChild(QLabel, "formBuilder.pictureWarning")
        assert warning is not None and warning.isVisible()
        assert "text replaces this picture" in warning.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_delete_on_an_icon_state_clears_it_in_the_same_step(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("save.png", "dot.png"))
    icon = "<normaloff>:/icons/save.png</normaloff><disabledoff>:/icons/dot.png</disabledoff>:/icons/save.png"
    window, pane, session, realizer = _pane(qapp, _form(icon=icon), str(tmp_path / "form.ui"))
    try:
        _select(session, "ok")
        pane.flush()
        steps = len(session.log.entries())
        _open_row(pane, "formBuilder.row.icon", qapp)
        popover = _search(qapp).window()
        other = popover.findChild(QToolButton, "formBuilder.iconOtherStates")
        assert other is not None
        other.click()
        disabled = popover.findChild(QToolButton, "formBuilder.iconState.disabledoff")
        normal = popover.findChild(QToolButton, "formBuilder.iconState.normaloff")
        assert disabled is not None and normal is not None
        disabled.click()
        disabled.setFocus()
        label = popover.findChild(QLabel, "formBuilder.iconPictureLabel")
        assert label is not None and label.text() == "Picture for disabled, off"
        _press(disabled, Qt.Key.Key_Delete)
        assert "<disabledoff>" not in session.text()
        assert "<normaloff>:/icons/save.png</normaloff>" in session.text()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        assert len(session.log.entries()) == steps + 1
    finally:
        _close(window, pane, realizer, session, qapp)
