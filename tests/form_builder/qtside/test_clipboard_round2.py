# pyright: reportAttributeAccessIssue=false
"""Round-2 clipboard behavior on a live Qt surface."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from app.qt.QtCore import QEvent, QMimeData, QObject, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QApplication, QLineEdit, QListWidget, QMenu, QPushButton, QWidget
from app.qt.qt_compat import delete_now

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.clipboard_actions import apply_command, clipboard_has_fragment
from app.features.form_builder.integration.context_menu import add_clipboard_actions
from app.features.form_builder.integration.pieces import SavedPieceStore
from app.features.form_builder.integration.workbench import InsertPane
from app.features.form_builder.qtside.canvas.core.palette import MIME_FRAGMENT
from app.features.form_builder.qtside.inspector.editors.sizing import SizeBody
from tests.form_builder.engine.commands._support import BOX, button_spec, nid
from tests.form_builder.qtside.support import open_session, opened

pytestmark = pytest.mark.usefixtures("qapp")

_THREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="top"><property name="text"><string>Top</string></property></widget></item>
   <item><widget class="QPushButton" name="middle"><property name="text"><string>Mid</string></property></widget></item>
   <item><widget class="QPushButton" name="bottom"><property name="text"><string>Bot</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Host:
    def __init__(self, session: FormSession) -> None:
        self._session = session
        self.sentences: List[str] = []
        self.problems: List[str] = []

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

    def show_paste_problem(self, text: str) -> None:
        self.problems.append(text)

    def save_selected_piece(self) -> None:
        return None


class _Keys(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.seen: List[int] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        kind = getattr(getattr(QEvent, "Type", QEvent), "KeyPress")
        if event.type() == kind:
            self.seen.append(int(event.key()))  # type: ignore[attr-defined]
        return False


def _park_focus(qapp) -> QWidget:  # type: ignore[no-untyped-def]
    sink = QWidget()
    sink.setObjectName("formBuilder.focusSink")
    sink.show()
    sink.setFocus()
    qapp.processEvents()
    return sink


def _names(session: FormSession) -> tuple:
    layout = session.document.root.layout
    assert layout is not None
    found = []
    for item in layout.items:
        content = item.content
        if content is not None:
            found.append(getattr(content, "object_name", ""))
    return tuple(found)


@pytest.mark.parametrize(
    "command_id",
    (
        "form.action.copy",
        "form.action.cut",
        "form.action.paste",
        "form.action.duplicate",
        "form.action.delete",
        "form.action.backspace",
        "form.action.selectAllSiblings",
    ),
)
def test_form_commands_stay_out_of_the_inline_editor(qapp, command_id: str) -> None:  # type: ignore[no-untyped-def]
    session = open_session(_THREE, "/tmp/cbcs-editor.ui")
    canvas = QWidget()
    canvas.setObjectName("formBuilder.canvas")
    editor = QLineEdit(canvas)
    editor.setText("Phone")
    editor.selectAll()
    keys = _Keys()
    editor.installEventFilter(keys)
    canvas.show()
    editor.setFocus()
    qapp.processEvents()
    try:
        before = _names(session)
        host = _Host(session)
        assert apply_command(host, command_id) is True
        assert _names(session) == before
        if command_id == "form.action.duplicate":
            assert int(getattr(Qt, "Key_D")) in keys.seen
    finally:
        session.dispose()
        canvas.deleteLater()
        qapp.processEvents()


def test_select_all_siblings_selects_the_row(qapp) -> None:  # type: ignore[no-untyped-def]
    sink = _park_focus(qapp)
    session = open_session(BOX, "/tmp/cbcs-siblings.ui")
    try:
        button = nid(session.document, "okButton")
        session.selection.set((button,), current=button, source=SelectionSource.COMMAND)
        host = _Host(session)
        assert apply_command(host, "form.action.selectAllSiblings") is True
        assert set(session.selection.state.ids) == {
            nid(session.document, "okButton"),
            nid(session.document, "label"),
        }
    finally:
        session.dispose()
        sink.deleteLater()


def test_paste_is_disabled_when_the_clipboard_has_text(qapp) -> None:  # type: ignore[no-untyped-def]
    sink = _park_focus(qapp)
    mime = QMimeData()
    mime.setText("hello")
    QApplication.clipboard().setMimeData(mime)
    assert clipboard_has_fragment() is False
    session = open_session(BOX, "/tmp/cbcs-menu.ui")
    try:
        menu = QMenu()
        add_clipboard_actions(
            menu,
            lambda _command: None,
            lambda command_id: command_id != "form.action.paste",
        )
        paste = [action for action in menu.actions() if action.text().startswith("Paste")]
        assert len(paste) == 1
        assert paste[0].isEnabled() is False
        assert "Ctrl+V" in paste[0].text()
        host = _Host(session)
        apply_command(host, "form.action.paste")
        assert host.sentences == ["The clipboard has text, not widgets."]
    finally:
        session.dispose()
        sink.deleteLater()


def test_two_insert_panes_share_saved_pieces(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    first = open_session(_THREE, "/tmp/cbcs-piece-a.ui")
    second = open_session(BOX, "/tmp/cbcs-piece-b.ui")
    parent = QWidget()
    try:
        store = SavedPieceStore(str(tmp_path))
        pane_a = InsertPane(lambda _collapsed: None, parent)
        pane_b = InsertPane(lambda _collapsed: None, parent)
        pane_a.bind_pieces(store)
        pane_b.bind_pieces(store)
        pane_a.bind_session(first)
        pane_b.bind_session(second)
        top = first.document.by_name("top")[0]
        first.selection.set((top,), current=top, source=SelectionSource.COMMAND)
        pane_a.save_selection(first)
        button = second.document.by_name("okButton")[0]
        second.selection.set((button,), current=button, source=SelectionSource.COMMAND)
        pane_b.save_selection(second)
        listed_a = pane_a.findChild(QListWidget, "formBuilder.savedPieces")
        listed_b = pane_b.findChild(QListWidget, "formBuilder.savedPieces")
        assert isinstance(listed_a, QListWidget)
        assert isinstance(listed_b, QListWidget)
        assert [listed_a.item(index).text() for index in range(listed_a.count())] == ["Top", "OK"]
        assert [listed_b.item(index).text() for index in range(listed_b.count())] == ["Top", "OK"]
        assert [piece.name for piece in store.load()] == ["Top", "OK"]
    finally:
        first.dispose()
        second.dispose()
        parent.deleteLater()


def test_enter_inserts_a_saved_piece(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    session = open_session(_THREE, "/tmp/cbcs-enter.ui")
    parent = QWidget()
    pasted: List[str] = []
    try:
        pane = InsertPane(lambda _collapsed: None, parent)
        pane.bind_pieces(SavedPieceStore(str(tmp_path)))
        pane.bind_session(session)
        pane.set_paste(lambda: pasted.append("paste"))
        middle = session.document.by_name("middle")[0]
        session.selection.set((middle,), current=middle, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        listed = pane.findChild(QListWidget, "formBuilder.savedPieces")
        assert isinstance(listed, QListWidget)
        listed.setCurrentRow(0)
        item = listed.item(0)
        assert item is not None
        assert item.toolTip().startswith("Insert Mid")
        kind = getattr(getattr(QEvent, "Type", QEvent), "KeyPress")
        listed.keyPressEvent(QKeyEvent(kind, getattr(Qt, "Key_Return"), getattr(Qt, "NoModifier")))
        assert pasted == ["paste"]
        assert clipboard_has_fragment() is True
    finally:
        session.dispose()
        parent.deleteLater()


def test_deleting_a_piece_offers_undo(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    session = open_session(_THREE, "/tmp/cbcs-undo-piece.ui")
    parent = QWidget()
    notes: List[tuple] = []
    try:
        pane = InsertPane(lambda _collapsed: None, parent)
        pane.bind_pieces(SavedPieceStore(str(tmp_path / "undo")))
        pane.bind_session(session)
        pane.set_notice(lambda sentence, undo: notes.append((sentence, undo)))
        middle = session.document.by_name("middle")[0]
        session.selection.set((middle,), current=middle, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        pane.delete_piece(0)
        listed = pane.findChild(QListWidget, "formBuilder.savedPieces")
        assert isinstance(listed, QListWidget)
        assert listed.count() == 0
        assert notes and notes[0][0] == "Deleted Mid."
        notes[0][1]()
        assert listed.count() == 1
        assert listed.item(0).text() == "Mid"
    finally:
        session.dispose()
        parent.deleteLater()


_BARE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Dialog</class>
 <widget class="QDialog" name="Dialog">
  <widget class="QLineEdit" name="nameEdit">
   <property name="geometry"><rect><x>20</x><y>30</y><width>160</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>40</x><y>80</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_a_paste_onto_a_shown_bare_dialog_shows_the_new_widget(qapp) -> None:  # type: ignore[no-untyped-def]
    with opened(_BARE) as (session, realizer):
        parent = QWidget()
        parent.resize(800, 600)
        host = _PasteHost(session)
        canvas = FormCanvas(session, realizer, host, parent)
        parent.show()
        qapp.processEvents()
        document = session.document
        root = realizer.root_widget
        assert root is not None
        session.selection.set((document.root.id,), current=document.root.id, source=SelectionSource.COMMAND)
        mime = QMimeData()
        mime.setData(MIME_FRAGMENT, write_fragment(Fragment(nodes=(button_spec("extra", "Extra"),))).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        assert apply_command(host, "form.action.paste") is True
        qapp.processEvents()
        extra = realizer.widget_for(document.by_name("extra")[0])
        kept = realizer.widget_for(document.by_name("okButton")[0])
        assert extra is not None and kept is not None
        assert extra.isVisibleTo(root)
        assert kept.isVisibleTo(root)
        assert document.root.layout is None
        canvas.dispose()
        parent.deleteLater()
        QApplication.clipboard().clear()


class _PasteHost:
    def __init__(self, session: FormSession) -> None:
        self._session = session
        self.sentences: List[str] = []

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

    def show_paste_problem(self, text: str) -> None:
        self.sentences.append(text)

    def save_selected_piece(self) -> None:
        return None

    def canvas_pressed(self) -> None:
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


def test_a_deleted_size_watch_does_not_raise(qapp) -> None:  # type: ignore[no-untyped-def]
    class _SizeHost:
        document = None
        owners: tuple = ()
        qt_names = False

        def live(self, owner: object) -> None:
            del owner
            return None

        def run(self, label: str, commands: object) -> None:
            del label, commands
            return None

        def editor_for(self, row: object, parent: QWidget) -> None:
            del row, parent
            raise AssertionError("unused")

        def layout(self, owner: object) -> None:
            del owner
            return None

    parent = QWidget()
    body = SizeBody(_SizeHost(), parent)  # type: ignore[arg-type]
    button = QPushButton()
    delete_now(button)
    body._watched = button
    body._watch_live(())
    assert body._watched is None
    parent.deleteLater()
    qapp.processEvents()
