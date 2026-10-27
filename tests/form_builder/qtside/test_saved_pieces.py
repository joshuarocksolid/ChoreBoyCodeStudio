# pyright: reportAttributeAccessIssue=false
"""Saved pieces live in global settings and in the insert pane."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QMimeData
from app.qt.QtWidgets import QLabel, QListWidget, QMenu, QWidget

from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.integration.pieces import (
    SavedPiece,
    SavedPieceStore,
    pieces_from_payload,
    payload_with_pieces,
    unique_piece_name,
)
from app.features.form_builder.integration.workbench import InsertPane
from app.features.form_builder.qtside.canvas.core.palette import MIME_NODE
from tests.form_builder.engine.commands._support import button_spec

pytestmark = pytest.mark.usefixtures("qapp")

_THREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="top"/></item>
   <item><widget class="QPushButton" name="middle"/></item>
   <item><widget class="QPushButton" name="bottom"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _xml() -> str:
    return write_fragment(Fragment(nodes=(button_spec("ok"),)))


def _open() -> FormSession:
    return FormSession.open(
        _THREE,
        path="/tmp/cbcs-pieces.ui",
        scope=FormScope(kind="external", ui_path="/tmp/cbcs-pieces.ui"),
    )


def _pane(parent: QWidget) -> InsertPane:
    pane = InsertPane(lambda _collapsed: None, parent)
    parent.show()
    pane.show()
    return pane


def _list(pane: InsertPane) -> QListWidget:
    listed = pane.findChild(QListWidget, "formBuilder.savedPieces")
    assert isinstance(listed, QListWidget)
    return listed


@pytest.mark.parity("R3-27")
def test_saved_pieces_round_trip_through_settings(tmp_path: Path) -> None:
    xml = _xml()
    payload = {
        "form_builder": {
            "workbench": {"left": 240},
            "saved_pieces": [
                {"name": "ok", "xml": xml},
                {"name": "", "xml": xml},
                {"name": "bad", "xml": "not a fragment"},
                "nope",
            ],
        }
    }
    kept = pieces_from_payload(payload)
    assert kept == (SavedPiece("ok", xml),)
    stored = payload_with_pieces(payload, kept)
    assert stored["form_builder"]["workbench"] == {"left": 240}
    assert stored["form_builder"]["saved_pieces"] == [{"name": "ok", "xml": xml}]
    store = SavedPieceStore(str(tmp_path))
    assert store.load() == ()
    store.replace(kept)
    assert SavedPieceStore(str(tmp_path)).load() == kept


def test_a_piece_name_collision_uses_the_engine_suffix() -> None:
    assert unique_piece_name("email", ()) == "email"
    assert unique_piece_name("email", ("email",)) == "email_2"
    assert unique_piece_name("email", ("email", "email_2")) == "email_3"


@pytest.mark.parity("R3-27")
def test_insert_pane_hides_the_piece_list_when_empty(qapp: object, tmp_path: Path) -> None:
    del qapp
    session = _open()
    parent = QWidget()
    try:
        pane = _pane(parent)
        pane.bind_pieces(SavedPieceStore(str(tmp_path)))
        pane.bind_session(session)
        listed = _list(pane)
        parent.show()
        pane.show()
        assert listed.isHidden()
        titles = [label.text() for label in pane.findChildren(QLabel) if label.text() == "Saved pieces"]
        assert titles == ["Saved pieces"]
        middle = session.document.by_name("middle")[0]
        session.selection.set((middle,), current=middle, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        assert not listed.isHidden()
        assert listed.count() == 1
        assert listed.item(0).text() == "middle"
        assert SavedPieceStore(str(tmp_path)).load()[0].name == "middle"
    finally:
        session.dispose()
        parent.deleteLater()


def test_dropping_a_selected_row_saves_the_whole_selection(qapp: object) -> None:
    del qapp
    session = _open()
    parent = QWidget()
    try:
        pane = _pane(parent)
        pane.bind_session(session)
        top = session.document.by_name("top")[0]
        middle = session.document.by_name("middle")[0]
        session.selection.set((top, middle), current=middle, source=SelectionSource.COMMAND)
        mime = QMimeData()
        mime.setData(MIME_NODE, str(int(middle)).encode("utf-8"))
        event = _Drop(mime)
        _list(pane).parent().dropEvent(event)  # type: ignore[attr-defined]
        assert event.accepted
        listed = _list(pane)
        assert listed.count() == 1
        assert listed.item(0).text() == "top"
        piece = pane.piece_at(0)
        assert piece is not None
        fragment = read_fragment(piece.xml)
        assert [node.field("object_name") for node in fragment.nodes] == ["top", "middle"]
        pane.save_selection(session)
        assert listed.item(1).text() == "top_2"
    finally:
        session.dispose()
        parent.deleteLater()


def test_the_piece_menu_deletes_the_row(qapp: object) -> None:
    del qapp
    session = _open()
    parent = QWidget()
    try:
        pane = _pane(parent)
        pane.bind_session(session)
        middle = session.document.by_name("middle")[0]
        session.selection.set((middle,), current=middle, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        menu = pane.piece_menu(0)
        assert isinstance(menu, QMenu)
        assert [action.text() for action in menu.actions()] == ["Rename", "Delete"]
        menu.actions()[1].trigger()
        listed = _list(pane)
        assert listed.count() == 0
        assert listed.isHidden()
    finally:
        session.dispose()
        parent.deleteLater()


class _Drop:
    def __init__(self, mime: QMimeData) -> None:
        self._mime = mime
        self.accepted = False

    def mimeData(self) -> QMimeData:
        return self._mime

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False
