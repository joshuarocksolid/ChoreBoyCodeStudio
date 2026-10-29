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


def test_item_icon_is_picked_in_the_session_and_matches_uic(qapp, tmp_path, monkeypatch) -> None:
    """The item details Icon row is the inspector icon editor; a pick is part of the one item step."""
    import os

    from app.qt.QtWidgets import QPushButton, QToolButton, QWidget
    from tests.form_builder.engine.codegen.uic_compare import compare
    from tests.form_builder.inspector.test_m43c_pictures import _UIC, _close, _pane, _press, _search, _seed, _select

    _seed(tmp_path, ("save.png", "dot.png"))
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QListWidget" name="choices">
   <item><property name="text"><string>Apple</string></property></item>
  </widget>
""",
    ).replace("</ui>", '<resources><include location="app.qrc"/></resources>\n</ui>')
    window, pane, session, realizer = _pane(qapp, text, str(tmp_path / "items.ui"))
    try:
        original = session.text()
        _select(session, "choices")
        pane.flush()
        next(item for item in pane.findChildren(QWidget, "formBuilder.itemsRow") if item.isVisible()).click()
        qapp.processEvents()
        editor = next(item for item in window.findChildren(ItemEditor) if item.isVisible())
        next(b for b in editor.findChildren(QToolButton) if b.accessibleName() == "Details of row 1").click()
        qapp.processEvents()
        icon = editor.findChild(QWidget, "formBuilder.itemIcon")
        assert icon is not None
        icon.findChild(QPushButton).click()
        search = _search(qapp)
        QTest.keyClicks(search, "dot")
        _press(search, Qt.Key.Key_Down)
        _press(search.parent().findChild(QWidget, "formBuilder.pictureGrid"), Qt.Key.Key_Return)
        assert editor.isVisible(), "a pick keeps the item editor open"
        # Esc in the icon popover closes that popover only; the pick stays.
        icon = editor.findChild(QWidget, "formBuilder.itemIcon")
        icon.findChild(QPushButton).click()
        _press(_search(qapp), Qt.Key.Key_Escape)
        assert editor.isVisible()
        editor.close_keep()
        qapp.processEvents()
        saved = session.text()
        assert "<normaloff>:/icons/dot.png</normaloff>" in saved
        assert session.log.undo_label() == "Edit items of choices"
        assert len(session.log.entries()) == 1
        (tmp_path / "items.ui").write_text(saved, encoding="utf-8")
        assert session.log.undo()
        assert session.text() == original
    finally:
        _close(window, pane, realizer, session, qapp)
    if os.path.isfile(_UIC):
        monkeypatch.setenv("CBCS_FB_UIC", _UIC)
        status, interesting, count, _total = compare(tmp_path / "items.ui")
        assert status == "ok", (interesting, count)


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


def _rows_ui(editor, object_name: str):
    """Visible list-editor fields under the tab whose list has ``object_name`` rows."""
    return [item for item in editor.findChildren(QLineEdit) if item.isVisible() and item.accessibleName().startswith(object_name)]


def test_moving_or_deleting_a_header_or_item_keeps_its_data(qapp) -> None:
    """A move or delete in a list carries each row's other data with it (cells, columns, details)."""
    from app.qt.QtWidgets import QTabWidget, QTableWidget

    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QTableWidget" name="sheet">
   <row><property name="text"><string>r1</string></property></row>
   <row><property name="text"><string>r2</string></property></row>
   <row><property name="text"><string>r3</string></property></row>
   <column><property name="text"><string>c1</string></property></column>
   <column><property name="text"><string>c2</string></property></column>
   <item row="0" column="0"><property name="text"><string>a0</string></property></item>
   <item row="0" column="1"><property name="text"><string>b0</string></property></item>
   <item row="1" column="0"><property name="text"><string>a1</string></property></item>
   <item row="2" column="1"><property name="text"><string>b2</string></property></item>
  </widget>
  <widget class="QTreeWidget" name="tree">
   <column><property name="text"><string>Name</string></property></column>
   <column><property name="text"><string>Colour</string></property></column>
   <column><property name="text"><string>Shape</string></property></column>
   <item>
    <property name="text"><string>Apple</string></property>
    <property name="toolTip"><string>name tip</string></property>
    <property name="text"><string>Red</string></property>
    <property name="toolTip"><string>colour tip</string></property>
    <property name="text"><string>Round</string></property>
   </item>
  </widget>
  <widget class="QListWidget" name="choices">
   <item><property name="text"><string>One</string></property><property name="toolTip"><string>first</string></property></item>
   <item><property name="text"><string>Two</string></property></item>
  </widget>
""",
    )
    session = open_session(text)
    original = write_ui(session.document).text
    sheet = session.document.by_name("sheet")[0]
    editor = open_editor(session, sheet, None)
    assert editor is not None
    tabs = editor.findChild(QTabWidget)
    tabs.setCurrentIndex(2)
    qapp.processEvents()
    first = _rows_ui(editor, "column row 1")[0]
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    tabs.setCurrentIndex(1)
    qapp.processEvents()
    middle = _rows_ui(editor, "row row 2")[0]
    middle.setFocus()
    QTest.keyClick(middle, Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)
    tabs.setCurrentIndex(0)
    qapp.processEvents()
    grid = editor.findChild(QTableWidget, "formBuilder.itemCells")
    shown = [[grid.item(r, c).text() if grid.item(r, c) else "" for c in range(grid.columnCount())] for r in range(grid.rowCount())]
    assert shown == [["b0", "a0"], ["b2", ""]]
    assert grid.horizontalHeaderItem(0).text() == "c2"
    editor.close_keep()
    assert session.log.undo_label() == "Edit items of sheet"

    tree = session.document.by_name("tree")[0]
    editor = open_editor(session, tree, None)
    tabs = editor.findChild(QTabWidget)
    tabs.setCurrentIndex(1)
    qapp.processEvents()
    shape = _rows_ui(editor, "Columns row 3")[0]
    shape.setFocus()
    QTest.keyClick(shape, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    editor.close_keep()
    draft = load_draft(session.document, tree)
    assert [column.text_at(0) for column in draft.columns] == ["Name", "Shape", "Colour"]
    assert draft.items[0].texts == ("Apple", "Round", "Red")
    written = write_ui(session.document).text
    apple = written[written.index("<string>Apple</string>"):]
    # The colour tooltip still follows the colour text in the file.
    assert apple.index("Red") < apple.index("colour tip")
    assert apple.index("name tip") < apple.index("Round") < apple.index("Red")

    choices = session.document.by_name("choices")[0]
    editor = open_editor(session, choices, None)
    one = _rows_ui(editor, "Items row 1")[0]
    one.setFocus()
    QTest.keyClick(one, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    editor.close_keep()
    items = load_draft(session.document, choices).items
    assert [item.text_at(0) for item in items] == ["Two", "One"]
    assert [entry.name for entry in items[1].base.properties] == ["text", "toolTip"]

    while session.log.undo_label() is not None:
        assert session.log.undo()
    assert write_ui(session.document).text == original
    session.dispose()


def test_table_cells_type_over_edit_keep_and_escape_cancels_only_the_cell(qapp) -> None:
    from app.qt.QtWidgets import QApplication, QTableWidget

    session = open_session(_form())
    sheet = session.document.by_name("sheet")[0]
    from app.qt.QtWidgets import QWidget

    host = QWidget()
    host.resize(600, 500)
    host.show()
    editor = open_editor(session, sheet, host)
    grid = editor.findChild(QTableWidget, "formBuilder.itemCells")
    grid.setFocus()
    qapp.processEvents()
    for char in "Hello":
        # Keys go where focus is, as typing does: the first one opens the cell.
        QTest.keyClicks(QApplication.focusWidget(), char)
        qapp.processEvents()
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Return)
    qapp.processEvents()
    assert load_draft(session.document, sheet).cells[0].text_at(0) == "Hello"
    grid.setCurrentCell(0, 0)
    grid.setFocus()
    QTest.keyClick(grid, Qt.Key.Key_Return)
    qapp.processEvents()
    field = QApplication.focusWidget()
    assert isinstance(field, QLineEdit) and field.text() == "Hello"
    field.end(False)
    QTest.keyClicks(field, " there")
    QTest.keyClick(field, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert editor.isVisible(), "Esc in a cell cancels the cell, not the session"
    assert load_draft(session.document, sheet).cells[0].text_at(0) == "Hello"
    editor.close_keep()
    assert session.log.undo_label() == "Edit items of sheet"
    host.close()
    session.dispose()


def test_inspector_items_row_opens_the_editor_and_another_selection_keeps(qapp) -> None:
    """The Content Items row is not the status tip: no changed bar, no Reset, and it opens the editor."""
    from app.qt.QtWidgets import QWidget
    from tests.form_builder.qtside.test_m43d_text import _close, _pane, _select, _settle

    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QComboBox" name="combo">
   <property name="statusTip"><string>Pick a size</string></property>
   <item><property name="text"><string>Small</string></property></item>
   <item><property name="text"><string>Large</string></property></item>
  </widget>
  <widget class="QLabel" name="other"/>
""",
    )
    window, pane, session, realizer = _pane(qapp, text)
    try:
        window.show()
        _select(session, "combo")
        _settle(qapp, pane)
        button = next(item for item in pane.findChildren(QWidget, "formBuilder.itemsRow") if item.isVisible())
        assert button.summary == "2 items: Small, Large"
        row = button.parentWidget()
        while row is not None and not row.objectName().startswith("formBuilder.row."):
            row = row.parentWidget()
        assert row is not None and row.objectName() == "formBuilder.row.items"
        bar = row.findChild(QWidget, "formBuilder.rowChanged")
        assert bar is None or bar.property("fbChanged") != "true"
        reset = row.findChild(QWidget, "formBuilder.rowReset")
        assert reset is None or not reset.isVisible()
        button.click()
        qapp.processEvents()
        editor = next(item for item in window.findChildren(ItemEditor) if item.isVisible())
        field = next(item for item in editor.findChildren(QLineEdit) if item.isVisible())
        QTest.keyClicks(field, "Tiny ")
        _select(session, "other")
        qapp.processEvents()
        qapp.processEvents()
        assert not [item for item in window.findChildren(ItemEditor) if item.isVisible()]
        assert session.log.undo_label() == "Edit items of combo"
        assert [item.text_at(0) for item in load_draft(session.document, session.document.by_name("combo")[0]).items][0] == "Tiny Small"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_list_item_details_read_and_flip_one_flag(qapp) -> None:
    """Details open on a checkable item, and a flag toggle keeps every other bit."""
    from app.qt.QtWidgets import QCheckBox, QComboBox, QWidget

    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QListWidget" name="choices">
   <item>
    <property name="text"><string>Apple</string></property>
    <property name="checkState"><enum>Checked</enum></property>
    <property name="flags"><set>ItemIsSelectable|ItemIsDragEnabled|ItemIsUserCheckable|ItemIsEnabled</set></property>
   </item>
  </widget>
""",
    )
    session = open_session(text)
    choices = session.document.by_name("choices")[0]
    host = QWidget()
    host.show()
    editor = open_editor(session, choices, host)
    field = next(item for item in editor.findChildren(QLineEdit) if item.isVisible())
    QTest.keyClick(field, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    starts = editor.findChild(QComboBox, "formBuilder.itemCheckState")
    assert starts is not None and starts.currentText() == "Checked"
    checkable = editor.findChild(QCheckBox, "formBuilder.itemFlag.ItemIsUserCheckable")
    assert checkable is not None and checkable.isChecked() and starts.isEnabled()
    editable = editor.findChild(QCheckBox, "formBuilder.itemFlag.ItemIsEditable")
    assert editable is not None and not editable.isChecked()
    editable.click()
    editor.close_keep()
    flags = next(entry for entry in load_draft(session.document, choices).items[0].base.properties if entry.name == "flags")
    assert flags.value.text == "ItemIsSelectable|ItemIsDragEnabled|ItemIsUserCheckable|ItemIsEnabled|ItemIsEditable"
    host.close()
    session.dispose()


def test_starts_is_off_until_the_user_can_check_the_item(qapp) -> None:
    from app.qt.QtWidgets import QCheckBox, QComboBox, QWidget

    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QListWidget" name="choices">
   <item>
    <property name="text"><string>Apple</string></property>
    <property name="flags"><set>ItemIsSelectable|ItemIsEnabled</set></property>
   </item>
  </widget>
""",
    )
    session = open_session(text)
    choices = session.document.by_name("choices")[0]
    host = QWidget()
    host.show()
    editor = open_editor(session, choices, host)
    field = next(item for item in editor.findChildren(QLineEdit) if item.isVisible())
    QTest.keyClick(field, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    starts = editor.findChild(QComboBox, "formBuilder.itemCheckState")
    checkable = editor.findChild(QCheckBox, "formBuilder.itemFlag.ItemIsUserCheckable")
    assert starts is not None and checkable is not None
    assert not checkable.isChecked()
    assert not starts.isEnabled()
    checkable.click()
    qapp.processEvents()
    assert starts.isEnabled()
    host.close()
    session.dispose()


def test_more_properties_shows_a_real_editor_for_each_row(qapp) -> None:
    from app.qt.QtWidgets import QApplication, QLabel, QToolButton, QWidget

    text = form(
        'class="QWidget" name="Form"',
        '<widget class="QListWidget" name="choices"><item><property name="text"><string>A</string></property></item></widget>',
    )
    session = open_session(text)
    host = QWidget()
    host.show()
    editor = open_editor(session, session.document.by_name("choices")[0], host)
    field = next(item for item in editor.findChildren(QLineEdit) if item.isVisible())
    QTest.keyClick(field, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    before = {id(widget) for widget in QApplication.topLevelWidgets() if widget.isVisible()}
    editor.findChild(QToolButton, "formBuilder.itemMore").click()
    qapp.processEvents()
    strays = [w for w in QApplication.topLevelWidgets() if w.isVisible() and id(w) not in before and w is not editor]
    panel = editor.findChild(QWidget, "formBuilder.itemMorePanel")
    labels = [label.text() for label in panel.findChildren(QLabel)]
    try:
        assert not strays, strays
        for name in ("Background", "Foreground"):
            assert name in labels
        assert labels.count("Font") == 1 and labels.count("Flags") == 1, labels
    finally:
        for stray in strays:
            stray.close()
            stray.deleteLater()
        editor.revert()
        host.close()
        session.dispose()


def test_table_cell_alt_right_opens_details_and_tooltip_is_one_undo_step(qapp) -> None:
    """Alt+Right on a cell opens the shared item details; Alt+Left closes them."""
    from app.qt.QtWidgets import QTableWidget, QWidget

    session = open_session(_form())
    sheet = session.document.by_name("sheet")[0]
    host = QWidget()
    host.resize(700, 640)
    host.show()
    editor = open_editor(session, sheet, host)
    assert editor is not None
    grid = editor.findChild(QTableWidget, "formBuilder.itemCells")
    assert grid is not None
    grid.setFocus()
    qapp.processEvents()
    QTest.keyClick(grid, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    details = editor.findChild(QWidget, "formBuilder.itemDetails")
    tip = editor.findChild(QLineEdit, "formBuilder.itemTooltip")
    assert details is not None and details.isVisible()
    assert tip is not None and tip.isVisible()
    tip.setFocus()
    QTest.keyClicks(tip, "Cell tip")
    QTest.keyClick(tip, Qt.Key.Key_Return)
    qapp.processEvents()
    grid.setFocus()
    QTest.keyClick(grid, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    assert not details.isVisible()
    editor.close_keep()
    saved = write_ui(session.document).text
    assert "<string>Cell tip</string>" in saved
    assert session.log.undo_label() == "Edit items of sheet"
    assert len(session.log.entries()) == 1
    host.close()
    session.dispose()
