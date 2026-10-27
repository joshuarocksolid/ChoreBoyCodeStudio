"""Copy, cut, paste, duplicate, and delete for one open form.

The clipboard write sits outside the command log. Paste, duplicate, and clone
are one ``InsertFragment``. Cut and delete are one ``DeleteNodes``.
"""

from __future__ import annotations

from typing import Protocol, Sequence, Tuple

from app.qt.QtCore import QMimeData
from app.qt.QtWidgets import QApplication, QLineEdit, QPlainTextEdit

from app.features.form_builder.engine.clipboard import (
    missing_connection_count,
    paste_anchor_name,
    paste_auto_layout,
    paste_placement,
    pasted_widget_count,
    plain_names,
    selectable_ids,
    selection_fragment,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import DeleteNodes, InsertFragment, InsertResult
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.qtside.canvas.core.palette import MIME_DESIGNER_FRAGMENT, MIME_FRAGMENT

CLIPBOARD_COMMAND_IDS = (
    "form.action.copy",
    "form.action.cut",
    "form.action.paste",
    "form.action.duplicate",
    "form.action.delete",
    "form.action.backspace",
    "form.action.selectAll",
    "form.action.savePiece",
)

SHORTCUT_COMMAND_IDS = (
    "form.action.copy",
    "form.action.cut",
    "form.action.paste",
    "form.action.duplicate",
    "form.action.delete",
    "form.action.backspace",
)

_TEXT_KEYS = frozenset(
    {
        "form.action.copy",
        "form.action.cut",
        "form.action.paste",
        "form.action.delete",
        "form.action.backspace",
    }
)


class ClipboardHost(Protocol):
    _session: FormSession

    def narrate(self, sentence: str) -> None:
        ...

    def show_paste_problem(self, text: str) -> None:
        ...

    def save_selected_piece(self) -> None:
        ...


def apply_command(host: ClipboardHost, command_id: str) -> bool:
    """Run a clipboard command. False when ``command_id`` is not one of them."""
    if command_id not in CLIPBOARD_COMMAND_IDS:
        return False
    if _forward_text_edit(command_id):
        return True
    session = host._session
    document = session.document
    ids = session.selection.state.ids
    if command_id == "form.action.copy":
        _copy(document, ids)
    elif command_id == "form.action.cut":
        _cut(session, ids)
    elif command_id == "form.action.paste":
        _paste(host, session, ids)
    elif command_id == "form.action.duplicate":
        _duplicate(host, session, ids)
    elif command_id in ("form.action.delete", "form.action.backspace"):
        _delete(session, ids)
    elif command_id == "form.action.selectAll":
        _select_all(session)
    elif command_id == "form.action.savePiece":
        host.save_selected_piece()
    return True


def _copy(document: UiDocument, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(document, ids)
    if not fragment.nodes:
        return
    _write(fragment)


def _cut(session: FormSession, ids: Sequence[NodeId]) -> None:
    targets = _deletable(session.document, ids)
    if not targets:
        return
    fragment = selection_fragment(session.document, targets)
    if not fragment.nodes:
        return
    _write(fragment)
    _execute_delete(session, targets)


def _paste(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    fragment = _read()
    if fragment is None:
        return
    _insert(host, session, ids, fragment, narrate=True)


def _duplicate(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(session.document, ids)
    if not fragment.nodes:
        return
    _insert(host, session, ids, fragment, narrate=False)


def _delete(session: FormSession, ids: Sequence[NodeId]) -> None:
    targets = _deletable(session.document, ids)
    if not targets:
        return
    _execute_delete(session, targets)


def _select_all(session: FormSession) -> None:
    document = session.document
    chosen = selectable_ids(document)
    if not chosen:
        return
    root = document.root.id
    current = root if root in chosen else chosen[0]
    session.selection.set(chosen, current=current, source=SelectionSource.COMMAND)


def _insert(
    host: ClipboardHost,
    session: FormSession,
    ids: Sequence[NodeId],
    fragment: Fragment,
    *,
    narrate: bool,
) -> None:
    document = session.document
    anchor = paste_anchor_name(document, ids)
    placement = paste_placement(document, ids)
    count = pasted_widget_count(fragment)
    try:
        outcome = session.log.execute(
            InsertFragment(placement, fragment, auto_layout=paste_auto_layout(placement))
        )
    except CommandRejected:
        return
    result = outcome.result
    if outcome.noop or not isinstance(result, InsertResult):
        return
    if narrate:
        host.narrate("Pasted %d widgets after %s" % (count, anchor))
    if not result.dangling:
        return
    gaps = missing_connection_count(fragment, result.renames, document.names())
    if gaps < 1:
        gaps = len(result.dangling)
    host.show_paste_problem(
        "Pasted %d widgets. %d connection points at a widget that isn't on this form." % (count, gaps)
    )


def _execute_delete(session: FormSession, targets: Tuple[NodeId, ...]) -> None:
    try:
        session.log.execute(DeleteNodes(targets))
    except CommandRejected:
        return


def _deletable(document: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    root = document.root.id
    ui = document.ui.id
    return tuple(
        node_id
        for node_id in ids
        if node_id != root and node_id != ui and document.contains(node_id)
    )


def _write(fragment: Fragment) -> None:
    xml = write_fragment(fragment).encode("utf-8")
    mime = QMimeData()
    mime.setData(MIME_FRAGMENT, xml)
    mime.setData(MIME_DESIGNER_FRAGMENT, xml)
    mime.setText(plain_names(fragment))
    QApplication.clipboard().setMimeData(mime)


def _read() -> Fragment | None:
    mime = QApplication.clipboard().mimeData()
    if mime is None:
        return None
    for name in (MIME_FRAGMENT, MIME_DESIGNER_FRAGMENT):
        if mime.hasFormat(name):
            return _parse(bytes(mime.data(name)).decode("utf-8"))
    if mime.hasText():
        return _parse(mime.text())
    return None


def _parse(text: str) -> Fragment | None:
    if not text.strip():
        return None
    try:
        fragment = read_fragment(text)
    except UiReadError:
        return None
    if not fragment.nodes:
        return None
    return fragment


def _forward_text_edit(command_id: str) -> bool:
    if command_id not in _TEXT_KEYS:
        return False
    widget = QApplication.focusWidget()
    if not isinstance(widget, (QLineEdit, QPlainTextEdit)):
        return False
    if command_id == "form.action.copy":
        widget.copy()
    elif command_id == "form.action.cut":
        widget.cut()
    elif command_id == "form.action.paste":
        widget.paste()
    elif command_id == "form.action.delete":
        _delete_in_edit(widget)
    elif command_id == "form.action.backspace":
        _backspace_in_edit(widget)
    return True


def _delete_in_edit(widget: QLineEdit | QPlainTextEdit) -> None:
    if isinstance(widget, QLineEdit):
        widget.del_()
        return
    cursor = widget.textCursor()
    cursor.deleteChar()
    widget.setTextCursor(cursor)


def _backspace_in_edit(widget: QLineEdit | QPlainTextEdit) -> None:
    if isinstance(widget, QLineEdit):
        widget.backspace()
        return
    cursor = widget.textCursor()
    cursor.deletePreviousChar()
    widget.setTextCursor(cursor)
