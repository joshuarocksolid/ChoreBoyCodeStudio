# pyright: reportAttributeAccessIssue=false
"""Clipboard commands through the Qt clipboard. The log sees one insert or one delete."""

from __future__ import annotations

from typing import List, Tuple

import pytest

from app.qt.QtCore import QMimeData
from app.qt.QtWidgets import QApplication, QLineEdit, QMenu

from app.features.form_builder.engine.clipboard import selection_fragment
from app.features.form_builder.engine.commands.catalog import InsertFragment
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropIndicator, DropPayload
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.integration.canvas import _drop_payload
from app.features.form_builder.integration.clipboard_actions import apply_command
from app.features.form_builder.integration.context_menu import add_clipboard_actions
from app.features.form_builder.qtside.canvas.core.palette import MIME_DESIGNER_FRAGMENT, MIME_FRAGMENT
from tests.form_builder.engine.commands._support import GRID, button_spec, cell_of, nid
from tests.form_builder.qtside.support import opened

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


class _Host:
    def __init__(self, session: FormSession) -> None:
        self._session = session
        self.sentences: List[str] = []
        self.problems: List[str] = []
        self.saved = 0

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

    def show_paste_problem(self, text: str) -> None:
        self.problems.append(text)

    def save_selected_piece(self) -> None:
        self.saved += 1


def _open(text: str) -> FormSession:
    return FormSession.open(text, path="/tmp/cbcs-clip-actions.ui", scope=FormScope(kind="external", ui_path="/tmp/cbcs-clip-actions.ui"))


def _select(session: FormSession, name: str) -> None:
    node_id = nid(session.document, name)
    session.selection.set((node_id,), current=node_id, source=SelectionSource.COMMAND)


def _box_names(doc: UiDocument) -> Tuple[str, ...]:
    layout = doc.root.layout
    assert layout is not None
    names = []
    for item in layout.items:
        content = item.content
        if isinstance(content, WidgetNode):
            names.append(content.object_name)
    return tuple(names)


def _fragment_xml() -> str:
    mime = QApplication.clipboard().mimeData()
    assert mime is not None
    assert mime.hasFormat(MIME_FRAGMENT)
    raw = bytes(mime.data(MIME_FRAGMENT))
    assert bytes(mime.data(MIME_DESIGNER_FRAGMENT)) == raw
    return raw.decode("utf-8")


@pytest.mark.pain("P-3")
@pytest.mark.parity("R3-23")
def test_pasting_the_middle_button_inserts_it_and_selects_it(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        _select(session, "middle")
        assert apply_command(host, "form.action.copy") is True
        assert "middle" in _fragment_xml()
        assert apply_command(host, "form.action.paste") is True
        assert _box_names(session.document) == ("top", "middle", "middle_2", "bottom")
        current = session.selection.state.current
        assert current is not None
        pasted = session.document.node(current)
        assert isinstance(pasted, WidgetNode)
        assert pasted.object_name == "middle_2"
        assert host.sentences == ["Pasted 1 widgets after middle"]
        session.log.undo()
        assert _box_names(session.document) == ("top", "middle", "bottom")
    finally:
        session.dispose()


def test_pasting_into_a_grid_uses_the_next_empty_cell(qapp: object) -> None:
    del qapp
    session = _open(GRID)
    try:
        host = _Host(session)
        _select(session, "b")
        apply_command(host, "form.action.copy")
        apply_command(host, "form.action.paste")
        assert cell_of(session.document, "b_2") == (1, 1)
    finally:
        session.dispose()


def test_duplicate_does_not_change_the_clipboard(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        _select(session, "top")
        apply_command(host, "form.action.copy")
        before = _fragment_xml()
        _select(session, "middle")
        apply_command(host, "form.action.duplicate")
        assert _fragment_xml() == before
        assert _box_names(session.document) == ("top", "middle", "middle_2", "bottom")
        assert host.sentences == []
    finally:
        session.dispose()


def test_cut_undo_restores_the_widgets_and_leaves_the_clipboard(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        _select(session, "middle")
        apply_command(host, "form.action.cut")
        assert _box_names(session.document) == ("top", "bottom")
        held = _fragment_xml()
        assert "middle" in held
        session.log.undo()
        assert _box_names(session.document) == ("top", "middle", "bottom")
        assert _fragment_xml() == held
    finally:
        session.dispose()


def test_delete_skips_the_root_and_an_empty_selection(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        apply_command(host, "form.action.delete")
        assert _box_names(session.document) == ("top", "middle", "bottom")
        session.selection.set((session.document.root.id,), current=session.document.root.id, source=SelectionSource.COMMAND)
        apply_command(host, "form.action.backspace")
        assert _box_names(session.document) == ("top", "middle", "bottom")
        _select(session, "bottom")
        apply_command(host, "form.action.delete")
        assert _box_names(session.document) == ("top", "middle")
    finally:
        session.dispose()


@pytest.mark.parity("R3-24")
def test_select_all_selects_every_widget_and_layout(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        apply_command(host, "form.action.selectAll")
        chosen = session.selection.state.ids
        document = session.document
        assert document.ui.id not in chosen
        assert document.root.id in chosen
        assert nid(document, "top") in chosen
        assert nid(document, "middle") in chosen
        assert nid(document, "bottom") in chosen
        layout = document.root.layout
        assert layout is not None
        assert layout.id in chosen
        assert session.selection.state.current == document.root.id
    finally:
        session.dispose()


def test_a_missing_connection_end_offers_show(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        _select(session, "middle")
        fragment = Fragment(
            nodes=(button_spec("fresh"),),
            connections=(
                NodeSpec(
                    "connection",
                    None,
                    (
                        ("sender", "fresh"),
                        ("signal", "clicked()"),
                        ("receiver", "ghost"),
                        ("slot", "clear()"),
                    ),
                ),
            ),
        )
        mime = QMimeData()
        mime.setData(MIME_FRAGMENT, write_fragment(fragment).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        apply_command(host, "form.action.paste")
        assert host.problems == [
            "Pasted 1 widgets. 1 connection points at a widget that isn't on this form."
        ]
        assert [row.code for row in session.diagnostics.all() if row.code == "FB014"] == ["FB014"]
        current = session.selection.state.current
        assert current is not None
        node = session.document.node(current)
        assert isinstance(node, WidgetNode)
        assert node.object_name == "fresh"
    finally:
        session.dispose()


def test_plain_text_pastes_only_when_it_is_a_fragment(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        host = _Host(session)
        _select(session, "middle")
        apply_command(host, "form.action.copy")
        xml = _fragment_xml()
        mime = QMimeData()
        mime.setText("not a form")
        QApplication.clipboard().setMimeData(mime)
        apply_command(host, "form.action.paste")
        assert _box_names(session.document) == ("top", "middle", "bottom")
        assert host.sentences == []
        mime = QMimeData()
        mime.setText(xml)
        QApplication.clipboard().setMimeData(mime)
        apply_command(host, "form.action.paste")
        assert _box_names(session.document) == ("top", "middle", "middle_2", "bottom")
    finally:
        session.dispose()


def test_a_focused_line_edit_keeps_its_own_paste(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    edit = QLineEdit()
    edit.setText("keep")
    edit.show()
    edit.setFocus()
    QApplication.processEvents()
    try:
        host = _Host(session)
        mime = QMimeData()
        mime.setText("from-clipboard")
        QApplication.clipboard().setMimeData(mime)
        assert QApplication.focusWidget() is edit
        apply_command(host, "form.action.paste")
        assert "keep" in edit.text()
        assert "from-clipboard" in edit.text()
        assert _box_names(session.document) == ("top", "middle", "bottom")
    finally:
        edit.close()
        session.dispose()


def test_a_fragment_mime_drop_inserts_without_source_ids(qapp: object) -> None:
    del qapp
    session = _open(_THREE)
    try:
        middle = nid(session.document, "middle")
        fragment = selection_fragment(session.document, (middle,))
        mime = QMimeData()
        mime.setData(MIME_FRAGMENT, write_fragment(fragment).encode("utf-8"))

        class _Event:
            def mimeData(self) -> QMimeData:
                return mime

        parsed = _drop_payload(_Event(), session.document)
        assert parsed is not None
        payload, key, carried = parsed
        assert isinstance(payload, DropPayload)
        assert payload.source_ids == ()
        assert key == ""
        assert carried is not None
        layout = session.document.root.layout
        assert layout is not None
        commands = commands_for(
            session.document,
            AcceptedDrop("", "", layout.id, "box", DropIndicator(Rect(0, 0, 1, 1)), Rect(0, 0, 1, 1), index=1),
            payload,
            carried,
        )
        assert len(commands) == 1
        assert isinstance(commands[0], InsertFragment)
    finally:
        session.dispose()


def test_the_context_menu_dispatches_clipboard_commands(qapp: object) -> None:
    del qapp
    menu = QMenu()
    seen: List[str] = []
    add_clipboard_actions(menu, seen.append)
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert labels == ["Copy", "Cut", "Paste", "Duplicate", "Delete", "Select all", "Save to pieces"]
    menu.actions()[0].trigger()
    assert seen == ["form.action.copy"]


def test_paste_leaves_the_widgets_that_were_already_on_the_form(qapp: object) -> None:
    del qapp
    with opened(_THREE) as (session, realizer):
        before = {}
        for name in ("Form", "top", "middle", "bottom"):
            widget = realizer.widget_for(session.document.by_name(name)[0])
            assert widget is not None
            before[name] = widget
        host = _Host(session)
        _select(session, "middle")
        assert apply_command(host, "form.action.copy") is True
        assert apply_command(host, "form.action.paste") is True
        assert realizer.last_stats.fallback_rebuilds == 0
        for name, widget in before.items():
            assert realizer.widget_for(session.document.by_name(name)[0]) is widget
        assert session.document.by_name("middle_2")
