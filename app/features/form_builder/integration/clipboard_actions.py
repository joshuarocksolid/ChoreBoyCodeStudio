"""Copy, cut, paste, duplicate, and delete for one open form.

The clipboard write sits outside the command log. Paste, duplicate, and clone
are one ``InsertFragment``. Cut and delete are one ``DeleteNodes``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Protocol, Sequence, Tuple

from app.qt import QtWidgets
from app.qt.QtCore import QMimeData, QPoint
from app.qt.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpacerItem,
    QTextEdit,
    QWidget,
)
from app.qt.qt_compat import delete_now

from app.features.form_builder.engine.clipboard import (
    CopiedBox,
    cut_sentence,
    dangling_sentence,
    duplicate_sentence,
    fragment_source_ids,
    plan_paste,
    paste_sentence,
    pasted_widget_count,
    plain_names,
    selectable_ids,
    selection_fragment,
    sibling_ids,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import DeleteNodes, InsertFragment, InsertResult
from app.features.form_builder.engine.commands.participants import default_registry
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as action_query
from app.features.form_builder.engine.query.drop_target import CENTRAL_NOTE, central_redirect
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue
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

# The last copy's measured pieces, keyed by its XML. The clipboard holds only
# the fragment; this lets a paste on another form size laid-out pieces the way
# they looked when copied. Text that is not this XML never uses it.
_LAST_COPY: Optional[Tuple[str, Tuple[Optional[CopiedBox], ...]]] = None


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
        _copy(host, document, ids)
    elif command_id == "form.action.cut":
        _cut(host, session, ids)
    elif command_id == "form.action.paste":
        _paste(host, session, ids)
    elif command_id == "form.action.duplicate":
        _duplicate(host, session, ids)
    elif command_id in ("form.action.delete", "form.action.backspace"):
        _delete(host, session, ids)
    elif command_id == "form.action.selectAll":
        _select_all(session)
    elif command_id == "form.action.selectAllSiblings":
        _select_siblings(session)
    elif command_id == "form.action.savePiece":
        host.save_selected_piece()
    return True


def _copy(host: ClipboardHost, document: UiDocument, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(document, ids)
    if not fragment.nodes:
        return
    _write(fragment, _boxes(host, fragment, fragment_source_ids(document, ids)))


def _cut(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    targets = _deletable(session.document, ids)
    if not targets:
        return
    fragment = selection_fragment(session.document, targets)
    if not fragment.nodes:
        return
    _write(fragment, _boxes(host, fragment, fragment_source_ids(session.document, targets)))
    _execute_delete(session, targets, "Cut")
    count = pasted_widget_count(fragment) or len(targets)
    host.narrate(cut_sentence(count))


def _paste(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    text = _clipboard_xml()
    fragment = _parse(text) if text is not None else None
    if fragment is None:
        notice = clipboard_text_notice()
        if notice is not None:
            host.narrate(notice)
        return
    copied = _copied_boxes(text, fragment)
    _insert(host, session, ids, fragment, undo_label="Paste", copied=copied)


def _duplicate(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    fragment = selection_fragment(session.document, ids)
    if not fragment.nodes:
        return
    copied = _boxes(host, fragment, fragment_source_ids(session.document, ids))
    _insert(host, session, ids, fragment, undo_label="Duplicate", copied=copied)


CENTRAL_REFUSAL = "The central area belongs to the window. Delete what's inside it instead."


def _delete(host: ClipboardHost, session: FormSession, ids: Sequence[NodeId]) -> None:
    document = session.document
    central = [part.id for part in action_query.parts(document)["central"]] if action_query.is_main_window(document) else []
    if len(ids) == 1 and ids[0] in central:
        host.narrate(CENTRAL_REFUSAL)  # UX-MAIN-014, from the outline and the Edit menu too
        return
    targets = _deletable(session.document, ids)
    if not targets:
        return
    sentence = _reference_sentence(session, targets)
    ask = getattr(host, "ask_delete", None)
    if sentence and ask is not None:
        ask(sentence, tuple(targets))
        return
    _execute_delete(session, targets)


def _reference_sentence(session: FormSession, targets: Sequence[NodeId]) -> str:
    """The outline's delete question. Empty when nothing else names these widgets."""
    document = session.document
    names = []
    for node_id in targets:
        node = document.get(node_id)
        name = getattr(node, "object_name", "") or ""
        if name and len(document.by_name(name)) > 1:
            return ""
        if name:
            names.append(name)
    prose = []
    seen = set()
    participants = default_registry().all()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        sentence = session.refs.ask_sentence(document, name, participants)
        if sentence:
            prose.append(sentence)
    return " ".join(prose)


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
    copied: Optional[Sequence[Optional[CopiedBox]]] = None,
) -> None:
    document = session.document
    # UX-MAIN-016: with a toolbar, menu or status bar selected, widgets land in the central area.
    central = central_redirect(document, ids[0] if ids else None)
    redirected = central is not None and all(spec.kind == "widget" for spec in fragment.nodes)
    if central is not None and redirected:
        ids = [central]
    count = pasted_widget_count(fragment)
    known = {id(spec): box for spec, box in zip(fragment.nodes, copied or ()) if box is not None}

    def measure(spec: NodeSpec) -> Optional[CopiedBox]:
        return known.get(id(spec)) or _measure(host, spec)

    placement, fragment, auto_layout = plan_paste(document, ids, fragment, measure)
    try:
        outcome = session.log.execute(
            InsertFragment(
                placement,
                fragment,
                auto_layout=auto_layout,
                undo_label=undo_label,
            )
        )
    except CommandRejected:
        host.narrate("Paste could not land here.")
        return
    result = outcome.result
    if outcome.noop or not isinstance(result, InsertResult):
        return
    if redirected:
        host.narrate(CENTRAL_NOTE)
    elif undo_label == "Duplicate":
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


def _measure(host: ClipboardHost, spec: NodeSpec) -> Optional[CopiedBox]:
    fresh = _fresh_box(spec)
    live = _live_source(host, spec)
    if fresh is not None:
        if live is not None and live.x is not None and live.y is not None:
            return CopiedBox(fresh.width, fresh.height, live.x, live.y)
        return fresh
    return live


def _fresh_box(spec: NodeSpec) -> Optional[CopiedBox]:
    if spec.kind != "widget":
        return None
    widget_class = getattr(QtWidgets, str(spec.field("class_name") or ""), None)
    if not isinstance(widget_class, type) or not issubclass(widget_class, QWidget):
        return None
    try:
        widget = widget_class()
    except (TypeError, RuntimeError):
        return None
    try:
        for entry in spec.properties:
            if entry.name in ("text", "title") and isinstance(entry.value, (StringValue, CStringValue)):
                _call_with(widget, "setText" if entry.name == "text" else "setTitle", entry.value.text)
        hint = widget.sizeHint()
        if hint.width() <= 0 or hint.height() <= 0:
            return None
        return CopiedBox(int(hint.width()), int(hint.height()))
    finally:
        delete_now(widget)


def _live_source(host: ClipboardHost, spec: NodeSpec) -> Optional[CopiedBox]:
    find = getattr(host, "realized_object", None)
    if not callable(find) or spec.id is None:
        return None
    document = host._session.document
    if not document.contains(spec.id):
        return None
    node = document.node(spec.id)
    if node.kind != spec.kind:
        return None
    spec_class = spec.field("class_name")
    if spec_class is not None and node.field("class_name") != spec_class:
        return None
    root = find(document.root.id)
    found = find(spec.id)
    if not isinstance(root, QWidget):
        return None
    if isinstance(found, QWidget):
        hint = found.sizeHint()
        corner = found.mapTo(root, QPoint(0, 0))
    elif isinstance(found, QLayout):
        hint = found.sizeHint()
        owner = found.parentWidget()
        if owner is None:
            return None
        corner = owner.mapTo(root, found.geometry().topLeft())
    elif isinstance(found, QSpacerItem):
        hint = found.sizeHint()
        return CopiedBox(max(1, int(hint.width())), max(1, int(hint.height())))
    else:
        return None
    if hint.width() <= 0 or hint.height() <= 0:
        return None
    return CopiedBox(int(hint.width()), int(hint.height()), int(corner.x()), int(corner.y()))


def _call_with(widget: QWidget, name: str, value: str) -> None:
    method = getattr(widget, name, None)
    if callable(method):
        method(value)


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


def _write(fragment: Fragment, boxes: Tuple[Optional[CopiedBox], ...] = ()) -> None:
    global _LAST_COPY
    xml = write_fragment(fragment)
    _LAST_COPY = (xml, boxes) if boxes else None
    raw = xml.encode("utf-8")
    mime = QMimeData()
    mime.setData(MIME_FRAGMENT, raw)
    mime.setData(MIME_DESIGNER_FRAGMENT, raw)
    mime.setText(plain_names(fragment))
    QApplication.clipboard().setMimeData(mime)


def _read() -> Fragment | None:
    text = _clipboard_xml()
    return _parse(text) if text is not None else None


def _clipboard_xml() -> Optional[str]:
    mime = QApplication.clipboard().mimeData()
    if mime is None:
        return None
    for name in (MIME_FRAGMENT, MIME_DESIGNER_FRAGMENT):
        if mime.hasFormat(name):
            return bytes(mime.data(name)).decode("utf-8")
    if mime.hasText():
        return mime.text()
    return None


def _boxes(
    host: ClipboardHost,
    fragment: Fragment,
    source_ids: Sequence[NodeId],
) -> Tuple[Optional[CopiedBox], ...]:
    """Live sizes and spots of the copied pieces, taken while the source is on screen."""
    found: List[Optional[CopiedBox]] = []
    for index, spec in enumerate(fragment.nodes):
        stamped = replace(spec, id=source_ids[index]) if index < len(source_ids) else spec
        found.append(_live_source(host, stamped))
    boxes = tuple(found)
    return boxes if any(box is not None for box in boxes) else ()


def _copied_boxes(text: Optional[str], fragment: Fragment) -> Optional[Tuple[Optional[CopiedBox], ...]]:
    """What this process measured when it copied ``text``. None for anything else."""
    if _LAST_COPY is None or text != _LAST_COPY[0] or len(_LAST_COPY[1]) != len(fragment.nodes):
        return None
    return _LAST_COPY[1]


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
    # Duplicate has no text meaning. The key is not re-sent: a synthetic
    # Ctrl+D would hit the same canvas or outline shortcut and run this again.
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
