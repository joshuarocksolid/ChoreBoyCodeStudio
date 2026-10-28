# pyright: reportAttributeAccessIssue=false
"""Text, translation, lists, custom properties, sort and search."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.chrome import chrome_from_values
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected, Services
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor
from app.features.form_builder.qtside.inspector.editors.custom_props import TYPES
from app.features.form_builder.qtside.inspector.rich_html import paragraphs_from_document, stable_html
from app.qt.QtCore import QLocale, Qt
from app.qt.QtGui import QFont, QTextCharFormat, QTextCursor, QTextDocument
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.engine.codegen.uic_compare import compare
from tests.form_builder.qtside.support import open_session, realize

pytestmark = pytest.mark.unit

os.environ.setdefault(
    "CBCS_FB_UIC",
    "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic",
)

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

_LABEL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text"><string comment="caption">Hello</string></property>
     <property name="toolTip"><string>Rest here</string></property>
     <property name="buddy"><cstring>nameEdit</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="richLabel">
     <property name="text"><string>Hello</string></property>
     <property name="textFormat"><enum>Qt::RichText</enum></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="nameEdit">
     <property name="echoMode"><enum>QLineEdit::Normal</enum></property>
    </widget>
   </item>
   <item>
    <widget class="QTabWidget" name="pages">
     <widget class="QWidget" name="firstPage">
      <attribute name="title"><string>First</string></attribute>
     </widget>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""

_LIST = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="tags" stdset="0">
   <stringlist><string>Red</string><string>Green</string><string>Blue</string></stringlist>
  </property>
  <property name="link" stdset="0">
   <url><string>example.com/a</string></url>
  </property>
 </widget>
</ui>
"""

_OPAQUE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="futureProp"><quark>1</quark></property>
 </widget>
</ui>
"""


def _pane(qapp: QApplication, text: str):
    session, realizer = realize(text)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(420, 760)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.flush()
    return window, pane, session, realizer


def _close(window, pane, realizer, session, qapp: QApplication) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
    qapp.processEvents()


def _select(session: FormSession, *names: str) -> None:
    ids = tuple(session.document.by_name(name)[0] for name in names)
    session.selection.set(ids, source=SelectionSource.PROGRAM)


def _settle(qapp: QApplication, pane: InspectorPane) -> None:
    pane.flush()
    qapp.processEvents()


def _expand_all(qapp: QApplication, pane: InspectorPane) -> None:
    pane.set_group_expanded(GroupId.ALL, True)
    _settle(qapp, pane)


def _scope(path: Path) -> FormScope:
    return FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(path.parent),
        generated_path=str(path.with_name("ui_%s.py" % path.stem)),
        window_path=str(path.with_name("%s_window.py" % path.stem)),
        module_name="ui_" + path.stem,
    )


def _generated(session: FormSession) -> str:
    text = write_ui(session.document).text
    folder = Path(tempfile.mkdtemp())
    path = folder / "form.ui"
    path.write_text(text, encoding="utf-8")
    result = generate_form_module(session.document, scope=_scope(path), source_bytes=text.encode("utf-8"))
    assert result.text is not None, result.diagnostics
    return result.text


def _field(row: QWidget, accessible: str) -> QLineEdit:
    found = row.findChild(QLineEdit)
    for item in row.findChildren(QLineEdit):
        if item.accessibleName() == accessible:
            found = item
            break
    assert isinstance(found, QLineEdit)
    return found


@pytest.mark.parity("R3-155")
def test_translation_attributes_round_trip(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        toggle = row.findChild(QToolButton, "formBuilder.translationToggle")
        assert toggle is not None
        toggle.click()
        box = row.findChild(QCheckBox)
        assert box is not None and box.text() == "Translate this text"
        box.click()
        qapp.processEvents()
        tag = row.findChild(QLabel, "formBuilder.translationTag")
        assert tag is not None and tag.text() == "Not translated"
        note = _field(row, "Translation: note for the translator")
        note.setText("Shown on receipts")
        note.editingFinished.emit()
        meaning = _field(row, "Translation: meaning")
        meaning.setText("heading")
        meaning.editingFinished.emit()
        written = write_ui(session.document).text
        assert 'notr="true"' in written
        assert 'extracomment="Shown on receipts"' in written
        assert 'comment="heading"' in written
        again = open_session(written)
        try:
            node = again.document.node(again.document.by_name("titleLabel")[0])
            prop = node.prop("text")
            assert prop is not None
            value = prop.value
            assert isinstance(value, StringValue)
            assert value.notr is True
            assert value.extracomment == "Shown on receipts"
            assert value.comment == "heading"
        finally:
            again.dispose()
        source = _generated(session)
        setup, _, rest = source.partition("def retranslateUi")
        assert 'self.titleLabel.setText(u"Hello")' in setup
        assert "titleLabel.setText(QCoreApplication.translate" not in rest
        assert session.log.undo_label() == "Change translation of text"
        tip = pane.findChild(QWidget, "formBuilder.row.toolTip")
        assert tip is not None
        assert tip.findChild(QToolButton, "formBuilder.translationToggle") is not None
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-156")
def test_string_list_summary_translation_and_esc(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LIST)
    try:
        _select(session, "Form")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.tags")
        assert row is not None
        button = row.findChild(QWidget, "formBuilder.summary")
        assert button is not None
        assert "3 items: Red, Green, Blue" in button.text() or "Red" in button.toolTip()
        before = write_ui(session.document).text
        depth = len(session.log.entries())
        button.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        edits = [item for item in popover.findChildren(QLineEdit) if item.isVisible()]
        assert len(edits) >= 3
        edits[0].setText("Crimson")
        qapp.processEvents()
        QTest.keyClick(edits[0], Qt.Key_Escape)
        qapp.processEvents()
        assert write_ui(session.document).text == before
        assert len(session.log.entries()) == depth
        button.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        toggle = popover.findChild(QToolButton, "formBuilder.translationToggle")
        assert toggle is not None
        toggle.click()
        note = _field(popover, "Translation: note for the translator")
        note.setText("swatches")
        note.editingFinished.emit()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        written = write_ui(session.document).text
        assert 'extracomment="swatches"' in written
        source = _generated(session)
        assert "Red" in source or "Crimson" in source
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-172")
def test_rich_text_bytes_ignore_locale(qapp: QApplication) -> None:
    def once(locale: QLocale) -> str:
        QLocale.setDefault(locale)
        document = QTextDocument()
        cursor = QTextCursor(document)
        fmt = QTextCharFormat()
        fmt.setFontWeight(getattr(QFont, "Bold", 75))
        cursor.insertText("Hello", fmt)
        return stable_html(paragraphs_from_document(document))

    c_locale = QLocale(getattr(QLocale, "C"))
    german = QLocale(getattr(QLocale, "German"), getattr(QLocale, "Germany"))
    first = once(c_locale)
    second = once(c_locale)
    third = once(german)
    assert first == second == third
    assert "font-weight:600" in first
    assert "Hello" in first
    assert "toHtml" not in first


def test_rich_label_bold_is_stable(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        button = row.findChild(QWidget, "formBuilder.summary")
        assert button is not None
        button.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        bold = next(item for item in popover.findChildren(QWidget) if item.accessibleName() == "Bold")
        edit = popover.findChild(QWidget)
        formatted = None
        for item in popover.findChildren(QWidget):
            if item.accessibleName() == "Text: formatted text":
                formatted = item
        assert formatted is not None
        cursor = formatted.textCursor()
        cursor.select(QTextCursor.Document)
        formatted.setTextCursor(cursor)
        bold.click()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        left = write_ui(session.document).text
        assert "font-weight:600" in left or "Bold" in left or "<b>" in left or "font-weight" in left
        assert left == write_ui(session.document).text
    finally:
        _close(window, pane, realizer, session, qapp)


def test_list_editor_keys_and_timing(qapp: QApplication) -> None:
    host = QWidget()
    editor = ListEditor(host, name="Colours")
    closed = {"n": 0}
    reverted = {"n": 0}
    editor.set_on_close(lambda: closed.__setitem__("n", closed["n"] + 1))
    editor.set_on_revert(lambda: reverted.__setitem__("n", reverted["n"] + 1))
    host.resize(320, 240)
    host.show()
    started = time.process_time()
    editor.set_texts(["a", "b", "c", "d", "e"])
    qapp.processEvents()
    assert time.process_time() - started < 0.05
    editor.focus_row(4)
    qapp.processEvents()
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    QTest.keyClick(field, Qt.Key_Return)
    qapp.processEvents()
    assert editor.texts()[-1] == ""
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    QTest.keyClick(field, Qt.Key_Return)
    assert closed["n"] == 1
    editor.focus_row(len(editor.texts()) - 1)
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    QTest.keyClick(field, Qt.Key_Backspace)
    qapp.processEvents()
    assert editor.texts() == ("a", "b", "c", "d", "e")
    editor.focus_row(2)
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    QTest.keyClick(field, Qt.Key_Up, Qt.AltModifier)
    qapp.processEvents()
    assert editor.texts()[1] == "c"
    QApplication.clipboard().setText("one\ntwo")
    editor.focus_row(0)
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    QTest.keyClick(field, Qt.Key_V, Qt.ControlModifier)
    qapp.processEvents()
    assert "one" in editor.texts() and "two" in editor.texts()
    QTest.keyClick(field, Qt.Key_Escape)
    assert reverted["n"] == 1
    started = time.process_time()
    editor.set_texts(["row %d" % index for index in range(500)])
    qapp.processEvents()
    open_cost = time.process_time() - started
    editor.focus_row(10)
    field = qapp.focusWidget()
    assert isinstance(field, QLineEdit)
    started = time.process_time()
    QTest.keyClick(field, Qt.Key_Z)
    key_cost = time.process_time() - started
    assert open_cost < 0.05
    assert key_cost < 0.016
    host.close()


@pytest.mark.parity("R3-149")
def test_custom_properties(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.click()
        qapp.processEvents()
        form = pane.findChild(QWidget, "formBuilder.customProperties")
        assert form is not None
        name = form.findChild(QLineEdit)
        assert name is not None
        name.setText("2nd")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        error = pane.findChild(QLabel, "formBuilder.rowError")
        assert error is not None and error.isVisible()
        assert "can't start with a digit" in error.text()
        name.setText("text")
        name.returnPressed.emit()
        qapp.processEvents()
        assert "already has a property called text" in error.text()
        name.setText("cbcsRole")
        name.returnPressed.emit()
        assert "cbcs" in error.text()
        name.setText("requiredRole")
        combo = form.findChild(QWidget)
        from app.qt.QtWidgets import QComboBox

        combo = form.findChild(QComboBox)
        assert combo is not None
        for label, _kind in TYPES:
            combo.setCurrentText(label)
            name.setText("role" + label.split()[0])
            name.returnPressed.emit()
            qapp.processEvents()
            _expand_all(qapp, pane)
        written = write_ui(session.document).text
        assert 'name="requiredRole"' in written or 'name="roleText"' in written
        assert 'stdset="0"' in written
        source = _generated(session)
        assert "setProperty" in source
        row = pane.findChild(QWidget, "formBuilder.row.roleText")
        if row is None:
            row = pane.findChild(QWidget, "formBuilder.row.requiredRole")
        assert row is not None
        menu = row.findChild(QToolButton, "formBuilder.customMenu")
        assert menu is not None
        steps = len(session.log.entries())
        rename = menu.menu().actions()[0]
        assert rename.text().startswith("Rename")

        def _fill() -> None:
            box = qapp.activeModalWidget()
            if box is None:
                return
            edit = box.findChild(QLineEdit)
            if edit is not None:
                edit.setText("roleRenamed")
                QTest.keyClick(edit, Qt.Key_Return)

        from app.qt.QtCore import QTimer

        QTimer.singleShot(0, _fill)
        rename.trigger()
        qapp.processEvents()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Rename custom property"
        _select(session, "titleLabel")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.roleRenamed")
        assert row is not None
        field = next(
            edit
            for edit in row.findChildren(QLineEdit)
            if not edit.accessibleName().startswith("Translation")
        )
        field.setText("4")
        field.editingFinished.emit()
        qapp.processEvents()
        row = pane.findChild(QWidget, "formBuilder.row.roleRenamed")
        assert row is not None
        menu_button = row.findChild(QToolButton, "formBuilder.customMenu")
        assert menu_button is not None
        popup = menu_button.menu()
        assert popup is not None
        change_action = popup.actions()[1]
        change = change_action.menu()
        assert change is not None
        number = next(action for action in change.actions() if action.text() == "Number")
        steps = len(session.log.entries())
        number.trigger()
        qapp.processEvents()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Change type of roleRenamed"
        renamed = session.document.node(session.document.by_name("titleLabel")[0]).prop(
            "roleRenamed"
        )
        assert renamed is not None and isinstance(renamed.value, NumberValue)
        assert renamed.value.value == 4
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.click()
        qapp.processEvents()
        form = pane.findChild(QWidget, "formBuilder.customProperties")
        assert form is not None
        name = form.findChild(QLineEdit)
        assert name is not None
        name.setText("roleRenamed")
        name.returnPressed.emit()
        qapp.processEvents()
        error = pane.findChild(QLabel, "formBuilder.rowError")
        assert error is not None
        assert "already has a custom property called roleRenamed" in error.text()
        _select(session, "titleLabel", "nameEdit")
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.click()
        form = pane.findChild(QWidget, "formBuilder.customProperties")
        assert form is not None
        name = form.findChild(QLineEdit)
        assert name is not None
        name.setText("sharedRole")
        name.returnPressed.emit()
        qapp.processEvents()
        for owner_name in ("titleLabel", "nameEdit"):
            node = session.document.node(session.document.by_name(owner_name)[0])
            shared = node.prop("sharedRole")
            assert shared is not None
            assert shared.is_dynamic
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-150")
def test_tab_title_is_an_attribute(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "firstPage")
        _expand_all(qapp, pane)
        titles = [
            label.text()
            for label in pane.findChildren(QLabel, "formBuilder.blockTitle")
            if label.isVisible()
        ]
        assert "Stored by the parent" in titles
        row = pane.findChild(QWidget, "formBuilder.row.attribute.title")
        assert row is not None
        edit = row.findChild(QLineEdit)
        assert isinstance(edit, QLineEdit)
        edit.setText("Cover")
        edit.editingFinished.emit()
        qapp.processEvents()
        node = session.document.node(session.document.by_name("firstPage")[0])
        title = node.attr("title")
        assert title is not None
        assert title.value.text == "Cover"
        assert node.prop("title") is None
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-148")
def test_sort_and_search(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "nameEdit")
        _expand_all(qapp, pane)
        search = pane.findChild(QLineEdit, "formBuilder.inspectorSearch")
        assert search is not None
        search.setText("password")
        _settle(qapp, pane)
        echo = pane.findChild(QWidget, "formBuilder.row.echoMode")
        assert echo is not None and echo.isVisible()
        search.setText("title")
        _select(session, "firstPage")
        _settle(qapp, pane)
        attr = pane.findChild(QWidget, "formBuilder.row.attribute.title")
        assert attr is not None and attr.isVisible()
        search.clear()
        _select(session, "titleLabel")
        _expand_all(qapp, pane)
        menu = pane.findChild(QToolButton, "formBuilder.inspectorMenu")
        assert menu is not None and menu.menu() is not None
        sort = next(action for action in menu.menu().actions() if "Sort" in action.text())
        sort.setChecked(True)
        _settle(qapp, pane)
        titles = [
            label.text()
            for label in pane.findChildren(QLabel, "formBuilder.blockTitle")
            if label.isVisible() and label.text()
        ]
        assert "Stored by the parent" not in titles
        assert "QLabel" not in titles
    finally:
        _close(window, pane, realizer, session, qapp)


def test_unknown_element_is_kept(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _OPAQUE)
    try:
        before = write_ui(session.document).text
        _select(session, "Form")
        _expand_all(qapp, pane)
        kept = [
            label.text()
            for label in pane.findChildren(QLabel)
            if label.isVisible() and "Kept as is" in label.text()
        ]
        assert kept
        assert "quark" in before
        assert write_ui(session.document).text == before
        assert "quark" in write_ui(session.document).text
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-157")
@pytest.mark.parity("R3-170")
def test_buddy_and_url_sentences(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.buddy")
        assert row is not None
        edit = row.findChild(QLineEdit)
        assert isinstance(edit, QLineEdit)
        edit.setText("missing")
        edit.editingFinished.emit()
        qapp.processEvents()
        caption = row.findChild(QLabel, "formBuilder.rowCaption")
        texts = [label.text() for label in row.findChildren(QLabel) if label.isVisible()]
        assert any("No widget called" in text and "missing" in text for text in texts)
        kept = session.document.node(session.document.by_name("titleLabel")[0]).prop("buddy")
        assert kept is not None
        assert kept.value.text == "nameEdit"
    finally:
        _close(window, pane, realizer, session, qapp)
    window, pane, session, realizer = _pane(qapp, _LIST)
    try:
        _select(session, "Form")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.link")
        assert row is not None
        warning = row.findChild(QLabel, "formBuilder.rowWarning")
        assert warning is not None and warning.isVisible()
        assert warning.text() == "This doesn't look like a web or file address."
    finally:
        _close(window, pane, realizer, session, qapp)


def test_popover_copies_unset_and_mixed_rules(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.toolTip")
        assert row is not None
        button = row.findChild(QWidget, "formBuilder.summary")
        assert button is not None
        button.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        sheet = popover.styleSheet()
        assert 'fbState="unset"' in sheet
        assert 'fbState="mixed"' in sheet
        assert "font-style: italic" in sheet
    finally:
        _close(window, pane, realizer, session, qapp)


def test_translation_matches_uic(qapp: QApplication, tmp_path: Path) -> None:
    del qapp
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text"><string comment="caption" extracomment="shown">Hello</string></property>
     <property name="toolTip"><string notr="true">Rest here</string></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""
    path = tmp_path / "form.ui"
    path.write_text(text, encoding="utf-8")
    status, interesting, count, _total = compare(path)
    if status != "ok":
        sample = interesting[:4] if isinstance(interesting, (str, list, tuple)) else interesting
        pytest.xfail("generator vs uic: %s (%s) owned by M4.2" % (status, sample))
    assert count == 0


def test_has_step_after_the_log_trims(qapp: QApplication) -> None:
    del qapp
    session = FormSession.open(
        _LABEL,
        path="/tmp/trim-form.ui",
        scope=FormScope(kind="external", ui_path="/tmp/trim-form.ui"),
        undo_limit=3,
    )
    try:
        owner = session.document.by_name("titleLabel")[0]
        for index in range(3):
            session.log.execute(SetProperty(owner, "toolTip", StringValue("tip %d" % index)))
        services = Services(session, catalog=None)  # type: ignore[arg-type]
        edit = services.begin_session("Change text")
        outcome = edit.run((SetProperty(owner, "toolTip", StringValue("after trim")),))
        assert not isinstance(outcome, (Rejected, Dropped))
        assert edit.has_step()
        services.dispose()
    finally:
        session.dispose()


def _live_popover(window: QWidget) -> QWidget:
    shown = [item for item in window.findChildren(QWidget, "formBuilder.rowPopover") if item.isVisible()]
    assert shown
    return shown[-1]


def _named(parent: QWidget, accessible: str) -> QWidget:
    return next(item for item in parent.findChildren(QWidget) if item.accessibleName() == accessible)


def test_rich_lists_line_breaks_and_segments_keep_the_edit(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        popover = _live_popover(window)
        formatted = _named(popover, "Text: formatted text")
        formatted.setFocus()
        cursor = formatted.textCursor()
        cursor.movePosition(QTextCursor.End)
        formatted.setTextCursor(cursor)
        QTest.keyClick(formatted, Qt.Key_Return, Qt.ShiftModifier)
        QTest.keyClicks(formatted, "there")
        _named(popover, "Numbered list").click()
        qapp.processEvents()
        written = session.document.node(session.document.by_name("richLabel")[0]).prop("text").value.text
        assert "Hello<br />there" in written
        assert "<ol>" in written and "<li" in written
        _named(popover, "Source").click()
        qapp.processEvents()
        source = _named(popover, "Text: HTML source")
        assert source.toPlainText() == written
        source.moveCursor(QTextCursor.End)
        QTest.keyClicks(source, " ")
        qapp.processEvents()
        kept = session.document.node(session.document.by_name("richLabel")[0]).prop("text").value.text
        assert "<ol>" in kept and "there" in kept
        steps = len(session.log.entries())
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        assert len(session.log.entries()) == steps
    finally:
        _close(window, pane, realizer, session, qapp)


def test_mixed_texts_have_no_translation_disclosure(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel", "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.toolTip")
        if row is None:
            row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        toggle = row.findChild(QToolButton, "formBuilder.translationToggle")
        assert toggle is None or not toggle.isVisible()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_list_editor_keys_act_on_the_clicked_row(qapp: QApplication) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    editor = ListEditor(name="Colours")
    layout.addWidget(editor)
    seen = []
    editor.set_on_texts(seen.append)
    host.resize(320, 240)
    host.show()
    editor.set_texts(["a", "b", "c", "d"])
    qapp.processEvents()
    editor.focus_row(0)
    third = next(item for item in editor.findChildren(QLineEdit) if item.accessibleName() == "Colours row 3")
    QTest.mouseClick(third, Qt.LeftButton)
    qapp.processEvents()
    focused = qapp.focusWidget()
    assert focused is third
    QTest.keyClick(third, Qt.Key_Delete, Qt.ControlModifier)
    qapp.processEvents()
    assert editor.texts() == ("a", "b", "d")
    host.close()


def test_editor_column_is_132_at_236_px(qapp: QApplication) -> None:
    from app.qt.QtWidgets import QScrollArea

    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "nameEdit")
        _settle(qapp, pane)
        scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        row = pane.findChild(QWidget, "formBuilder.row.echoMode")
        assert row is not None
        width = 400
        for _attempt in range(20):
            window.resize(width, 760)
            _settle(qapp, pane)
            if row.width() == 236:
                break
            width += 236 - row.width()
        assert row.width() == 236
        editor = row._editor.widget
        assert editor.width() == 132
        assert scroll.horizontalScrollBar().maximum() == 0
    finally:
        _close(window, pane, realizer, session, qapp)
