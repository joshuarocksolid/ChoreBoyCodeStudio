# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Tree item editor: windowed rows, sideways columns, kept column properties (UX-ITEM-004)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.items.editor import open_editor
from app.features.form_builder.qtside.items.model import load_draft, summary
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QLineEdit, QScrollArea
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.usefixtures("qapp")


def _prop(text: str) -> str:
    return '<property name="text"><string>%s</string></property>' % text


def _tree(columns: int, rows: int) -> str:
    parts = ["<column>%s</column>" % _prop("C%d" % c) for c in range(columns)]
    for r in range(rows):
        parts.append("<item>%s</item>" % _prop("Row %d" % r))
    return form('class="QWidget" name="Form"', '<widget class="QTreeWidget" name="tree">%s</widget>' % "".join(parts))


def _fields(editor):
    return [w for w in editor.findChildren(QLineEdit, "formBuilder.treeItem") if w.isVisible()]


def test_large_tree_builds_only_rows_in_view_and_scrolled_rows_edit_their_own_item(qapp) -> None:
    session = open_session(_tree(1, 400))
    tree = session.document.by_name("tree")[0]
    editor = open_editor(session, tree, None)
    assert editor is not None
    assert len(editor.findChildren(QLineEdit, "formBuilder.treeItem")) < 60
    scroll = editor.findChild(QScrollArea, "formBuilder.treeItemsScroll")
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum() // 2)
    qapp.processEvents()
    shown = _fields(editor)
    assert shown and all(field.text().startswith("Row ") for field in shown)
    target = shown[len(shown) // 2]
    number = int(target.text().split()[1])
    target.setFocus()
    QTest.keyClicks(target, "!")
    scroll.verticalScrollBar().setValue(0)
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum() // 2)
    qapp.processEvents()
    editor.close_keep()
    texts = [item.text_at(0) for item in load_draft(session.document, tree).items]
    assert texts[number] == "Row %d!" % number
    assert sum(1 for text in texts if text.endswith("!")) == 1
    assert len(session.log.entries()) == 1
    session.dispose()


def test_tree_columns_past_the_third_are_reachable_and_editable(qapp) -> None:
    session = open_session(_tree(5, 1))
    tree = session.document.by_name("tree")[0]
    editor = open_editor(session, tree, None)
    assert editor is not None
    fields = _fields(editor)
    assert len(fields) == 5
    qapp.processEvents()
    scroll = editor.findChild(QScrollArea, "formBuilder.treeItemsScroll")
    assert scroll.horizontalScrollBar().maximum() > 0
    last = fields[4]
    QTest.keyClick(fields[3], Qt.Key.Key_Right)
    QTest.keyClicks(last, "fifth")
    editor.close_keep()
    assert load_draft(session.document, tree).items[0].texts[-1] == "fifth"
    assert len(load_draft(session.document, tree).items[0].texts) == 5
    session.dispose()


def test_typing_in_a_new_column_keeps_the_column_two_tooltip_on_column_two(qapp) -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QTreeWidget" name="tree">
   <column><property name="text"><string>A</string></property></column>
   <column><property name="text"><string>B</string></property></column>
   <column><property name="text"><string>C</string></property></column>
   <item>
    <property name="text"><string>Apple</string></property>
    <property name="toolTip"><string>name tip</string></property>
    <property name="text"><string>Red</string></property>
    <property name="toolTip"><string>colour tip</string></property>
   </item>
  </widget>""",
    )
    session = open_session(text)
    tree = session.document.by_name("tree")[0]
    editor = open_editor(session, tree, None)
    fields = _fields(editor)
    fields[2].setFocus()
    QTest.keyClicks(fields[2], "Round")
    # Another keystroke in the same session must not move it either.
    QTest.keyClicks(fields[2], "s")
    editor.close_keep()
    written = write_ui(session.document).text
    apple = written[written.index("<string>Apple</string>"):]
    assert apple.index("name tip") < apple.index("Red") < apple.index("colour tip") < apple.index("Rounds")
    assert load_draft(session.document, tree).items[0].texts == ("Apple", "Red", "Rounds")
    session.dispose()
