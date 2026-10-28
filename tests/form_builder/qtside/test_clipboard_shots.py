# pyright: reportAttributeAccessIssue=false
"""Clipboard screenshots. Scene, size, and theme are in the filename."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pytest

from app.qt.QtCore import QMimeData
from app.qt.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QPushButton, QWidget
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.clipboard_actions import apply_command
from app.features.form_builder.integration.toast import CommandToast, ToastNote
from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.workbench import _PieceOps
from app.features.form_builder.qtside.insert.pane import InsertPane
from app.features.form_builder.qtside.canvas.core.palette import MIME_FRAGMENT
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.engine.commands._support import GRID, button_spec, cell_of
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_drop import _flush, _shown

pytestmark = pytest.mark.usefixtures("qapp")

_SIZES = ((1080, 600), (1400, 900))
_MODES = ("light", "dark")
_TOAST = "Pasted 1 widget. 1 connection points at a widget that isn't on this form."


class _Host:
    def __init__(self, session: FormSession) -> None:
        self._session = session
        self.toast: Optional[CommandToast] = None
        self.sentences: List[str] = []

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

    def show_paste_problem(self, text: str) -> None:
        assert self.toast is not None
        self.toast.show_note(ToastNote(text, "Show", "", 0), lambda _note: None)

    def save_selected_piece(self) -> None:
        return None


@pytest.mark.timeout(120)
def test_clipboard_screenshots(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        for width, height in _SIZES:
            _grab_grid(qapp, tokens, out, width, height, mode)
            _grab_toast(qapp, tokens, out, width, height, mode)
            _grab_pieces(qapp, tokens, out, width, height, mode)
            if (width, height) == (1400, 900):
                _grab_bare_paste(qapp, tokens, out, mode)
                _grab_form_row(qapp, tokens, out, mode)
                _grab_two_pieces(qapp, tokens, out, mode)


def _grab_grid(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with _shown(GRID) as (session, canvas, _host):
        shell = canvas.parentWidget()
        assert shell is not None
        shell.resize(width, height)
        canvas.resize(width, height)
        canvas.apply_theme(tokens)
        document = session.document
        first = document.by_name("a")[0]
        second = document.by_name("b")[0]
        session.selection.set((first, second), current=second, source=SelectionSource.COMMAND)
        host = _Host(session)
        assert apply_command(host, "form.action.copy") is True
        assert apply_command(host, "form.action.paste") is True
        assert cell_of(document, "a_2") == (1, 1)
        assert cell_of(document, "b_2") == (2, 1)
        chosen = session.selection.state.ids
        assert document.by_name("a_2")[0] in chosen
        assert document.by_name("b_2")[0] in chosen
        _flush()
        qapp.processEvents()
        shell.grab().save(str(out / ("clipboard-grid-paste-%s-%dx%d.png" % (mode, width, height))), "PNG")


def _grab_toast(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with opened(GRID) as (session, realizer):
        parent = QWidget()
        parent.resize(width, height)
        host = _Host(session)
        canvas = FormCanvas(session, realizer, host, parent)
        toast = CommandToast(parent)
        host.toast = toast
        canvas.apply_theme(tokens)
        toast.apply_theme(tokens)
        parent.show()
        canvas.resize(width, height)
        _flush()
        fragment = Fragment(
            nodes=(button_spec("note", "Note"),),
            connections=(
                NodeSpec(
                    "connection",
                    None,
                    (
                        ("sender", "note"),
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
        anchor = session.document.by_name("b")[0]
        session.selection.set((anchor,), current=anchor, source=SelectionSource.COMMAND)
        assert apply_command(host, "form.action.paste") is True
        label = toast.findChild(QLabel, "formBuilder.toastText")
        assert isinstance(label, QLabel)
        assert label.text() == _TOAST
        shown = [button for button in toast.findChildren(QPushButton) if button.text() == "Show"]
        assert len(shown) == 1
        parent.resize(width, height)
        toast.place()
        qapp.processEvents()
        parent.grab().save(str(out / ("clipboard-paste-toast-%s-%dx%d.png" % (mode, width, height))), "PNG")
        canvas.dispose()
        parent.deleteLater()


def _grab_pieces(qapp, tokens, out: Path, width: int, height: int, mode: str) -> None:  # type: ignore[no-untyped-def]
    with opened(GRID) as (session, realizer):
        shell = QWidget()
        shell.resize(width, height)
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        pane = InsertPane(lambda _collapsed: None, shell, memory=InMemoryInsertMemory(), pieces=_PieceOps())
        host = _Host(session)
        canvas = FormCanvas(session, realizer, host, shell)
        pane.setMaximumWidth(280)
        pane.bind_session(session)
        shell.setStyleSheet(
            "QWidget#formBuilder\\.insert { background: %s; color: %s; }"
            "QListWidget { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit { background: %s; color: %s; border: 1px solid %s; }"
            "QLabel#formBuilder\\.sectionTitle { color: %s; background: transparent; }"
            % (
                tokens.panel_bg,
                tokens.text_primary,
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                tokens.text_muted,
            )
        )
        pane.apply_chrome(chrome_for(tokens))
        canvas.apply_theme(tokens)
        row.addWidget(pane)
        row.addWidget(canvas, 1)
        chosen = session.document.by_name("a")[0]
        session.selection.set((chosen,), current=chosen, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        listed = pane.findChild(QListWidget, "formBuilder.savedPieces")
        assert isinstance(listed, QListWidget)
        assert not listed.isHidden()
        assert listed.count() == 1
        shell.show()
        qapp.processEvents()
        shell.grab().save(str(out / ("clipboard-saved-pieces-%s-%dx%d.png" % (mode, width, height))), "PNG")
        canvas.dispose()
        shell.deleteLater()


_BARE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Dialog</class>
 <widget class="QDialog" name="Dialog">
  <property name="geometry"><rect><x>0</x><y>0</y><width>520</width><height>400</height></rect></property>
  <widget class="QLineEdit" name="nameEdit">
   <property name="geometry"><rect><x>20</x><y>30</y><width>160</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>290</x><y>250</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_ROW = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowTitle"><string>Contact details</string></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget>
   </item>
   <item row="0" column="1"><widget class="QLineEdit" name="phone"/></item>
   <item row="1" column="0">
    <widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget>
   </item>
   <item row="1" column="1"><widget class="QLineEdit" name="email"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _grab_bare_paste(qapp, tokens, out: Path, mode: str) -> None:  # type: ignore[no-untyped-def]
    with opened(_BARE) as (session, realizer):
        parent = QWidget()
        parent.resize(1400, 900)
        host = _Host(session)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.apply_theme(tokens)
        parent.show()
        canvas.resize(1400, 900)
        document = session.document
        session.selection.set((document.root.id,), current=document.root.id, source=SelectionSource.COMMAND)
        mime = QMimeData()
        mime.setData(MIME_FRAGMENT, write_fragment(Fragment(nodes=(button_spec("extra", "Extra"),))).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        assert apply_command(host, "form.action.paste") is True
        assert document.root.layout is None
        _flush()
        qapp.processEvents()
        parent.grab().save(str(out / ("clipboard-bare-paste-%s-1400x900.png" % mode)), "PNG")
        canvas.dispose()
        parent.deleteLater()


def _grab_form_row(qapp, tokens, out: Path, mode: str) -> None:  # type: ignore[no-untyped-def]
    with opened(_ROW) as (session, realizer):
        parent = QWidget()
        parent.resize(1400, 900)
        host = _Host(session)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.apply_theme(tokens)
        parent.show()
        canvas.resize(1400, 900)
        document = session.document
        label = document.by_name("phoneLabel")[0]
        field = document.by_name("phone")[0]
        session.selection.set((label, field), current=field, source=SelectionSource.COMMAND)
        assert apply_command(host, "form.action.copy") is True
        email = document.by_name("email")[0]
        session.selection.set((email,), current=email, source=SelectionSource.COMMAND)
        assert apply_command(host, "form.action.paste") is True
        _flush()
        qapp.processEvents()
        parent.grab().save(str(out / ("clipboard-form-row-%s-1400x900.png" % mode)), "PNG")
        canvas.dispose()
        parent.deleteLater()


def _grab_two_pieces(qapp, tokens, out: Path, mode: str) -> None:  # type: ignore[no-untyped-def]
    with opened(_ROW) as (session, realizer):
        shell = QWidget()
        shell.resize(1400, 900)
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        pane = InsertPane(lambda _collapsed: None, shell, memory=InMemoryInsertMemory(), pieces=_PieceOps())
        host = _Host(session)
        canvas = FormCanvas(session, realizer, host, shell)
        pane.setMaximumWidth(280)
        pane.bind_session(session)
        pane.apply_chrome(chrome_for(tokens))
        canvas.apply_theme(tokens)
        row.addWidget(pane)
        row.addWidget(canvas, 1)
        phone = session.document.by_name("phoneLabel")[0]
        field = session.document.by_name("phone")[0]
        session.selection.set((phone, field), current=phone, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        email = session.document.by_name("emailLabel")[0]
        session.selection.set((email,), current=email, source=SelectionSource.COMMAND)
        pane.save_selection(session)
        listed = pane.findChild(QListWidget, "formBuilder.savedPieces")
        assert isinstance(listed, QListWidget)
        assert listed.count() == 2
        shell.show()
        qapp.processEvents()
        shell.grab().save(str(out / ("clipboard-two-pieces-%s-1400x900.png" % mode)), "PNG")
        canvas.dispose()
        shell.deleteLater()
