# pyright: reportAttributeAccessIssue=false
"""K14 item editors (UX_SPEC 12.3)."""

from __future__ import annotations

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.items.model import MODEL_VIEW_SENTENCE
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget
from tests.form_builder.qtside.support import form, opened

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="box">
   <item><widget class="QComboBox" name="combo"/></item>
   <item><widget class="QTreeWidget" name="tree"/></item>
   <item><widget class="QListView" name="view"/></item>
  </layout>
""",
)


class _Host:
    def __init__(self) -> None:
        self.sentences = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

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


def test_k14_combo_then_tree_then_model_view_then_undo(qapp) -> None:
    del qapp
    host = _Host()
    with opened(_FORM) as (session, realizer):
        original = write_ui(session.document).text
        parent = QWidget()
        parent.resize(800, 600)
        canvas = FormCanvas(session, realizer, host, parent)
        parent.show()
        combo = session.document.by_name("combo")[0]
        session.selection.set((combo,), current=combo, source=SelectionSource.CANVAS)
        canvas.setFocus()
        _key(canvas, "Key_Return")
        editor = _editor(parent)
        assert editor is not None
        edit = editor.findChild(QLineEdit)
        assert edit is not None
        QTest.keyClicks(edit, "Small")
        QTest.keyClick(edit, Qt.Key.Key_Return)
        second = next(item for item in editor.findChildren(QLineEdit) if item.isVisible() and item.text() == "")
        QTest.keyClicks(second, "Medium")
        QTest.keyClick(second, Qt.Key.Key_Return)
        third = next(item for item in editor.findChildren(QLineEdit) if item.isVisible() and item.text() == "")
        QTest.keyClicks(third, "Large")
        QTest.keyClick(third, Qt.Key.Key_Return)
        closing = next(item for item in editor.findChildren(QLineEdit) if item.isVisible() and item.text() == "")
        QTest.keyClick(closing, Qt.Key.Key_Return)
        assert _editor(parent) is None
        assert session.log.undo_label() == "Edit items of combo"
        assert len(session.log.entries()) == 1
        editor = _reopen(parent, canvas, combo, session)
        assert editor is not None
        QTest.keyClick(editor.findChild(QLineEdit), Qt.Key.Key_Down)
        QTest.keyClick(editor.findChild(QLineEdit), Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        assert _editor(parent) is None
        assert len(session.log.entries()) == 1
        tree = session.document.by_name("tree")[0]
        session.selection.set((tree,), current=tree, source=SelectionSource.CANVAS)
        _key(canvas, "Key_Return")
        editor = _editor(parent)
        assert editor is not None
        field = editor.findChild(QLineEdit, "formBuilder.treeItem")
        assert field is not None
        QTest.keyClicks(field, "Fruit")
        QTest.keyClick(field, Qt.Key.Key_Return)
        child = [item for item in editor.findChildren(QLineEdit, "formBuilder.treeItem") if item.text() == ""][-1]
        QTest.keyClicks(child, "Apple")
        QTest.keyClick(child, Qt.Key.Key_Tab)
        done = editor.findChild(QPushButton, "formBuilder.itemEditorDone")
        assert done is not None
        done.click()
        view = session.document.by_name("view")[0]
        session.selection.set((view,), current=view, source=SelectionSource.CANVAS)
        _key(canvas, "Key_Return")
        assert _editor(parent) is None
        assert host.sentences[-1] == MODEL_VIEW_SENTENCE
        while session.log.undo_label() is not None:
            assert session.log.undo()
        assert write_ui(session.document).text == original
        canvas.dispose()
        parent.deleteLater()


def _reopen(parent, canvas, node, session):
    session.selection.set((node,), current=node, source=SelectionSource.CANVAS)
    _key(canvas, "Key_Return")
    return _editor(parent)


def _editor(parent):
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    found = [item for item in parent.findChildren(QWidget, "formBuilder.itemEditor") if item.isVisible()]
    return found[-1] if found else None


def _key(canvas, name: str) -> None:
    QTest.keyClick(canvas, getattr(Qt.Key, name))
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
