# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Item editor sessions, pages group, and the model-view sentence."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.items.editor import ItemEditor, open_editor
from app.features.form_builder.qtside.items.model import MODEL_VIEW_SENTENCE, load_draft
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QLineEdit
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.usefixtures("qapp")


def _form() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <widget class="QComboBox" name="combo"/>
  <widget class="QListWidget" name="choices"/>
  <widget class="QTreeWidget" name="tree"/>
  <widget class="QTableWidget" name="sheet"/>
  <widget class="QListView" name="view"/>
  <widget class="QTabWidget" name="tabs">
   <property name="currentIndex"><number>0</number></property>
   <widget class="QWidget" name="tabA"><attribute name="title"><string>First</string></attribute></widget>
   <widget class="QWidget" name="tabB"><attribute name="title"><string>Second</string></attribute></widget>
  </widget>
""",
    )


def test_combo_session_is_one_step_and_escape_reverts(qapp) -> None:
    session = open_session(_form())
    original = write_ui(session.document).text
    combo = session.document.by_name("combo")[0]
    editor = open_editor(session, combo, None)
    assert editor is not None
    assert editor.findChild(QLineEdit) is not None
    edit = editor.findChild(QLineEdit)
    QTest.keyClicks(edit, "Small")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    edits = [edit for edit in editor.findChildren(QLineEdit) if edit.isVisible()]
    empty = next(edit for edit in edits if edit.text() == "")
    empty.setFocus()
    QTest.keyClicks(empty, "Medium")
    from app.qt.QtWidgets import QPushButton

    button = editor.findChild(QPushButton, "formBuilder.itemEditorDone")
    assert button is not None
    button.click()
    assert session.log.undo_label() == "Edit items of combo"
    assert len(session.log.entries()) == 1
    draft = load_draft(session.document, combo)
    assert draft is not None
    assert [item.text_at(0) for item in draft.items] == ["Small", "Medium"]
    assert session.log.undo()
    editor = open_editor(session, combo, None)
    assert editor is not None
    edit = editor.findChild(QLineEdit)
    QTest.keyClicks(edit, "Later")
    editor.revert()
    assert write_ui(session.document).text == original
    session.dispose()


@pytest.mark.xfail(strict=True, reason="M4.3c owns the picture picker (UX-PED-102); the Icon row stays disabled until that lane lands")
def test_icon_row_stays_disabled_until_m4_3c(qapp) -> None:
    """The picture picker is M4.3c (UX-PED-102). This fails until that lane lands."""
    del qapp
    session = open_session(_form())
    combo = session.document.by_name("combo")[0]
    editor = open_editor(session, combo, None)
    assert editor is not None
    from app.qt.QtWidgets import QToolButton

    more = editor.findChild(QToolButton)
    # The disclosure is on the row. Open details with Alt+Right.
    edit = editor.findChild(QLineEdit)
    QTest.keyClick(edit, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    icon = editor.findChild(type(editor), "formBuilder.itemIcon")
    from app.qt.QtWidgets import QLabel

    icon = editor.findChild(QLabel, "formBuilder.itemIcon")
    assert icon is not None and icon.isEnabled()
    session.dispose()


def test_pages_group_uses_the_menu_commands(qapp) -> None:
    from app.features.form_builder.engine.commands.catalog import MovePage, SetProperty
    from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
    from app.features.form_builder.qtside.inspector.editors.pages_list import PagesBody
    from app.qt.QtWidgets import QWidget

    session = open_session(_form())
    owner = session.document.by_name("tabs")[0]

    class Host:
        def __init__(self) -> None:
            self.owners = (owner,)
            self.session = session
            self.labels = []

        @property
        def document(self):
            return session.document

        def run(self, label, commands):
            self.labels.append((label, type(commands[0]).__name__))
            session.log.execute(commands[0])

        def live(self, _owner):
            return None

    host = Host()
    parent = QWidget()
    parent.resize(360, 240)
    body = PagesBody(host, parent)  # pyright: ignore[reportArgumentType]
    parent.show()
    body.show(())
    qapp.processEvents()
    def _edit():
        visible = [item for item in body.widget.findChildren(QLineEdit) if item.isVisible()]
        assert visible
        return visible[0]

    first = _edit()
    # Enter on the last row adds a page after it.
    visible = [item for item in body.widget.findChildren(QLineEdit) if item.isVisible()]
    visible[-1].setFocus()
    QTest.keyClick(visible[-1], Qt.Key.Key_Return)
    assert host.labels[-1][0] == InsertPage(owner).label
    row = _edit()
    row.setFocus()
    QTest.keyClick(row, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    assert any(label == MovePage(owner, 0, 1).label for label, _name in host.labels)
    row = _edit()
    QTest.keyClick(row, Qt.Key.Key_Space)
    assert ("Change start page", "SetProperty") in host.labels, host.labels
    row = _edit()
    QTest.keyClick(row, Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)
    assert any(label == DeletePage(owner, 0).label for label, _name in host.labels)
    parent.close()
    session.dispose()
    from app.features.form_builder.qtside.canvas.core.text import items_target

    session = open_session(_form())
    view = session.document.by_name("view")[0]
    combo = session.document.by_name("combo")[0]
    assert items_target(session.document, view) == "model"
    assert items_target(session.document, combo) == "items"
    assert "change it to a list widget" in MODEL_VIEW_SENTENCE
    session.dispose()


@pytest.mark.parity("R3-173")
def test_item_properties_round_trip_through_uic(tmp_path) -> None:
    import os
    from pathlib import Path

    from app.features.form_builder.engine.commands.catalog import SetItems
    from app.features.form_builder.qtside.items.model import commit_slots, load_draft
    from tests.form_builder.engine.commands._support import open_log

    uic = Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic")
    if uic.is_file():
        os.environ.setdefault("CBCS_FB_UIC", str(uic))
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QTreeWidget" name="tree">
   <column><property name="text"><string>One</string></property></column>
   <column><property name="text"><string>Two</string></property></column>
   <column><property name="text"><string>Three</string></property></column>
   <item>
    <property name="text"><string>Fruit</string></property>
    <property name="text"><string>Red</string></property>
    <property name="text"><string>Round</string></property>
    <item>
     <property name="text"><string>Apple</string></property>
    </item>
   </item>
  </widget>
""",
    )
    log = open_log(text)
    tree = log.document.by_name("tree")[0]
    draft = load_draft(log.document, tree)
    assert draft is not None
    assert draft.items[0].texts == ("Fruit", "Red", "Round")
    assert draft.items[0].children[0].text_at(0) == "Apple"
    items, _rows, columns = commit_slots(draft)
    log.execute(SetItems(tree, items, None, columns, merge_token="round", widget_name="tree"))
    written = write_ui(log.document).text
    again = open_log(written)
    reloaded = load_draft(again.document, again.document.by_name("tree")[0])
    assert reloaded is not None
    assert reloaded.items[0].texts == ("Fruit", "Red", "Round")
    assert reloaded.items[0].children[0].text_at(0) == "Apple"
    path = tmp_path / "items.ui"
    path.write_text(written, encoding="utf-8")
    from tests.form_builder.engine.codegen.uic_compare import compare

    outcome = compare(path)
    assert outcome[0] == "ok", outcome


@pytest.mark.xfail(strict=True, reason="codegen lane owns engine/codegen/emit.py: an item toolTip is emitted as item.setToolTip after the nested item rebinds that name")
def test_item_tooltip_matches_uic(tmp_path) -> None:
    import os
    from pathlib import Path

    uic = Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic")
    if uic.is_file():
        os.environ.setdefault("CBCS_FB_UIC", str(uic))
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QTreeWidget" name="tree">
   <item>
    <property name="text"><string>Fruit</string></property>
    <property name="toolTip"><string>tip</string></property>
    <property name="vendorNote"><string>kept</string></property>
    <item><property name="text"><string>Apple</string></property></item>
   </item>
  </widget>
""",
    )
    path = tmp_path / "tip.ui"
    path.write_text(text, encoding="utf-8")
    from tests.form_builder.engine.codegen.uic_compare import compare

    outcome = compare(path)
    assert outcome[0] == "ok", outcome

