"""Copy, cut, paste, duplicate, and delete for one open form.

The clipboard write sits outside the command log. Paste, duplicate, and clone
are one ``InsertFragment``. Cut and delete are one ``DeleteNodes``.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence, Tuple

from app.qt.QtCore import QEvent, QMimeData, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from app.features.form_builder.engine.clipboard import (
    cut_sentence,
    dangling_sentence,
    duplicate_sentence,
    paste_auto_layout,
    paste_placement,
    paste_sentence,
    pasted_widget_count,
    plain_names,
    selectable_ids,
    selection_fragment,
    sibling_ids,
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
    "form.action.selectAllSiblings",
    "form.action.savePiece",
)

SHORTCUT_COMMAND_IDS = (
    "form.action.copy",
    "form.action.cut",
    "form.action.paste",
    "form.action.duplicate",
    "form.action.delete",
    "form.action.backspace",
    "form.action.selectAllSiblings",
)

_TEXT_KEYS = frozenset(
    {
        "form.action.copy",
        "form.action.cut",
        "form.action.paste",
        "form.action.duplicate",
        "form.action.delete",
        "form.action.backspace",
        "form.action.selectAll",
        "form.action.selectAllSiblings",
    }
)

_PLAIN_TEXT = "The clipboard has text, not widgets."


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
        _cut(host, session, ids)
    elif command_id == "form.action.paste":
        _paste(host, session, ids)
    elif command_id == "form.action.duplicate":
        _duplicate(host, session, ids)
    elif command_id in ("form.action.delete", "form.action.backspace"):
        _delete(session, ids)
    elif command_id == "form.action.selectAll":
        _select_all(session)
    elif command_id == "form.action.selectAllSiblings":
        _select_siblings(session)
    elif command_id == "form.action.savePiece":
        host.save_selected_piece()
    return True


def _copy(document: UiDocument, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(document, ids)
    if not fragment.nodes:
        return
    _write(fragment)


def _cut(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    targets = _deletable(session.document, ids)
    if not targets:
        return
    fragment = selection_fragment(session.document, targets)
    if not fragment.nodes:
        return
    _write(fragment)
    _execute_delete(session, targets, "Cut")
    count = pasted_widget_count(fragment) or len(targets)
    host.narrate(cut_sentence(count))


def _paste(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    fragment = _read()
    if fragment is None:
        notice = clipboard_text_notice()
        if notice is not None:
            host.narrate(notice)
        return
    _insert(host, session, ids, fragment, undo_label="Paste")


def _duplicate(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(session.document, ids)
    if not fragment.nodes:
        return
    _insert(host, session, ids, fragment, undo_label="Duplicate")


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


def _select_siblings(session: FormSession) -> None:
    state = session.selection.state
    chosen = sibling_ids(session.document, state.current, state.ids)
    if not chosen:
        return
    current = state.current if state.current in chosen else chosen[0]
    session.selection.set(chosen, current=current, source=SelectionSource.COMMAND)


def _insert(
    host: ClipboardHost,
    session: FormSession,
    ids: Sequence[NodeId],
    fragment: Fragment,
    *,
    undo_label: str,
) -> None:
    document = session.document
    placement = paste_placement(document, ids)
    count = pasted_widget_count(fragment)
    try:
        outcome = session.log.execute(
            InsertFragment(
                placement,
                fragment,
                auto_layout=paste_auto_layout(placement),
                undo_label=undo_label,
            )
        )
    except CommandRejected:
        host.narrate("Paste could not land here.")
        return
    result = outcome.result
    if outcome.noop or not isinstance(result, InsertResult):
        return
    if undo_label == "Duplicate":
        host.narrate(duplicate_sentence(document, ids))
    else:
        host.narrate(paste_sentence(document, ids, count))
    sentence = dangling_sentence(fragment, result.dangling, result.renames, document.names())
    if sentence is not None:
        host.show_paste_problem(sentence)


def _execute_delete(session: FormSession, targets: Tuple[NodeId, ...], undo_label: str = "") -> None:
    try:
        session.log.execute(DeleteNodes(targets, undo_label=undo_label))
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


def publish_xml(xml: str) -> None:
    """Put fragment XML on the clipboard so paste can read it back."""
    raw = xml.encode("utf-8")
    mime = QMimeData()
    mime.setData(MIME_FRAGMENT, raw)
    mime.setData(MIME_DESIGNER_FRAGMENT, raw)
    QApplication.clipboard().setMimeData(mime)


def clipboard_has_fragment() -> bool:
    """True when paste can insert widgets."""
    return _read() is not None


def clipboard_text_notice() -> Optional[str]:
    """A sentence when the clipboard holds text that is not a fragment."""
    mime = QApplication.clipboard().mimeData()
    if mime is None or not mime.hasText() or not mime.text().strip():
        return None
    if _read() is not None:
        return None
    return _PLAIN_TEXT


def _write(fragment: Fragment) -> None:
    xml = write_fragment(fragment)
    raw = xml.encode("utf-8")
    mime = QMimeData()
    mime.setData(MIME_FRAGMENT, raw)
    mime.setData(MIME_DESIGNER_FRAGMENT, raw)
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
    if not isinstance(widget, QWidget) or not _is_text_input(widget):
        return False
    surface = _edit_surface(widget)
    if command_id == "form.action.copy":
        _call(surface, "copy")
    elif command_id == "form.action.cut":
        _call(surface, "cut")
    elif command_id == "form.action.paste":
        _call(surface, "paste")
    elif command_id == "form.action.delete":
        _delete_in_edit(surface)
    elif command_id == "form.action.backspace":
        _backspace_in_edit(surface)
    elif command_id in ("form.action.selectAll", "form.action.selectAllSiblings"):
        _call(surface, "selectAll")
    elif command_id == "form.action.duplicate":
        _send_chord(widget, "D")
    return True


def _is_text_input(widget: QWidget) -> bool:
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        return True
    return isinstance(widget, QComboBox) and widget.isEditable()


def _edit_surface(widget: QWidget) -> QWidget:
    if isinstance(widget, QComboBox):
        line = widget.lineEdit()
        return line if line is not None else widget
    if isinstance(widget, QAbstractSpinBox):
        line = widget.lineEdit()
        return line if line is not None else widget
    return widget


def _call(widget: QWidget, name: str) -> None:
    method = getattr(widget, name, None)
    if callable(method):
        method()


def _send_chord(widget: QWidget, letter: str) -> None:
    key = getattr(Qt, "Key_%s" % letter)
    modifiers = getattr(Qt, "ControlModifier")
    kind = getattr(QEvent, "Type", QEvent)
    text = letter.lower()
    QApplication.sendEvent(widget, QKeyEvent(getattr(kind, "KeyPress"), key, modifiers, text))
    QApplication.sendEvent(widget, QKeyEvent(getattr(kind, "KeyRelease"), key, modifiers, text))


def _delete_in_edit(widget: QWidget) -> None:
    if isinstance(widget, QLineEdit):
        widget.del_()
        return
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        cursor = widget.textCursor()
        cursor.deleteChar()
        widget.setTextCursor(cursor)


def _backspace_in_edit(widget: QWidget) -> None:
    if isinstance(widget, QLineEdit):
        widget.backspace()
        return
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        cursor = widget.textCursor()
        cursor.deletePreviousChar()
        widget.setTextCursor(cursor)
