"""Record a shortcut. A second chord within one second joins the first."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import CStringValue, StringValue, Value
from app.features.form_builder.qtside.inspector.api import (
    KEY_SEQUENCE,
    MIXED_TEXT,
    EditorHost,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import (
    PairColumn,
    name_part,
    owner_name,
    payload,
    qt_key,
    warning_color,
    yield_form_undo,
)
from app.qt.qt_compat import enum_value
from app.qt.QtCore import QEvent, QTimer, Qt
from app.qt.QtGui import QAction, QColor, QKeySequence
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

_WINDOW_MS = 1000
_MODIFIER_KEYS = ("Key_Shift", "Key_Control", "Key_Alt", "Key_Meta")


def _key_names() -> dict:
    names = {}
    enum = getattr(Qt, "Key", None)
    items = []
    if enum is not None and enum is not Qt:
        try:
            items = list(enum)
        except TypeError:
            items = []
    if items:
        for item in items:
            name = str(getattr(item, "name", "") or "")
            if name.startswith("Key_"):
                name = name[4:]
            if name:
                names[int(item)] = name
        return names
    for name in dir(Qt):
        if not name.startswith("Key_"):
            continue
        try:
            names[int(getattr(Qt, name))] = name[4:]
        except (TypeError, ValueError):
            continue
    return names


_KEY_NAMES = _key_names()


def _format() -> object:
    fmt = getattr(QKeySequence, "PortableText", None)
    if fmt is None:
        fmt = getattr(getattr(QKeySequence, "SequenceFormat", QKeySequence), "PortableText")
    return fmt


def _portable(sequence: QKeySequence) -> str:
    return str(sequence.toString(_format()))


def _chord_text(key: int, mods: int) -> str:
    """Portable text without building a QKeySequence inside the key event."""
    if key in tuple(int(qt_key(name)) for name in _MODIFIER_KEYS):
        return ""
    parts = []
    control = int(enum_value(_mod("ControlModifier")))
    alt = int(enum_value(_mod("AltModifier")))
    shift = int(enum_value(_mod("ShiftModifier")))
    meta = int(enum_value(_mod("MetaModifier")))
    if mods & control:
        parts.append("Ctrl")
    if mods & alt:
        parts.append("Alt")
    if mods & shift:
        parts.append("Shift")
    if mods & meta:
        parts.append("Meta")
    name = _KEY_NAMES.get(key, "")
    if not name:
        return ""
    parts.append(name)
    return "+".join(parts)


class _KeyField(QLineEdit):
    """Captures keys while recording. An app-wide filter crashed Qt's test sender."""

    def __init__(self, editor: "KeyEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self.setReadOnly(True)
        self.setPlaceholderText("None")

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        if getattr(self._editor, "recording", False):
            # Touching widgets or starting a timer inside this override crashes Qt's sender.
            self._editor._pending = (
                int(event.key()),  # type: ignore[attr-defined]
                event.modifiers(),  # type: ignore[attr-defined]
            )
            return
        super().keyPressEvent(event)


class _RecordButton(QPushButton):
    """Enter starts recording. A push button otherwise takes Space only."""

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key in (qt_key("Key_Return"), qt_key("Key_Enter")):
            self.click()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class KeyEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._shown = ""
        self._previous: Optional[Value] = None
        self._root = QWidget(parent)
        column = QVBoxLayout(self._root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self._edit = _KeyField(self, self._root)
        yield_form_undo(self._edit)
        self._record = _RecordButton("Record", self._root)
        self._record.setAutoDefault(False)
        self._record.clicked.connect(self._arm)
        column.addWidget(PairColumn(self._edit, self._record, "Ctrl+Shift+Alt+F12", self._root))
        self._warning = QLabel(self._root)
        self._warning.setObjectName("formBuilder.rowWarning")
        self._warning.setWordWrap(True)
        self._warning.hide()
        column.addWidget(self._warning)
        self._timer = QTimer(self._root)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._finish)
        self._kick = QTimer(self._root)
        self._kick.setInterval(30)
        self._kick.timeout.connect(self._drain)
        self._pending: Optional[tuple] = None
        self.recording = False
        self._first = ""
        self._armed_text = ""

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        name_part(self._edit, self._host, "keys")
        name_part(self._record, self._host, "record")
        self._previous = payload(value)
        text = "" if isinstance(value, Mixed) else _text(self._previous)
        self._shown = text
        if not self.recording:
            self._edit.setText(text)
            self._edit.setPlaceholderText(MIXED_TEXT if isinstance(value, Mixed) else "None")
        self._paint_clash(text)

    def is_dirty(self) -> bool:
        return self.recording or self._edit.text() != self._shown

    def _arm(self) -> None:
        if self.recording:
            return
        self.recording = True
        self._first = ""
        self._armed_text = self._shown
        self._edit.setText("Press the keys…")
        pair = self._edit.parentWidget()
        relayout = getattr(pair, "relayout", None)
        if callable(relayout):
            relayout()
        accent = getattr(self._host.chrome, "accent", "") or QColor(37, 99, 235).name()
        self._edit.setStyleSheet("border: 2px solid %s;" % accent)
        self._pending = None
        self._edit.setFocus()
        self._kick.start()

    def _drain(self) -> None:
        pending = self._pending
        self._pending = None
        if not isinstance(pending, tuple) or not self.recording:
            if not self.recording:
                self._kick.stop()
            return
        key, mods = pending
        self.from_codes(int(key), int(enum_value(mods)))

    def from_codes(self, key: int, mods: int) -> None:
        if not self.recording:
            return
        if key == int(qt_key("Key_Escape")):
            self._cancel()
            return
        if key == int(qt_key("Key_Backspace")) and mods == 0:
            self._stop()
            self._commit_text("")
            return
        chord = _chord_text(key, mods)
        if not chord:
            return
        if not self._first:
            self._first = chord
            self._edit.setText(chord)
            self._timer.start(_WINDOW_MS)
            return
        self._timer.stop()
        self._stop()
        self._commit_text("%s, %s" % (self._first, chord))

    def _finish(self) -> None:
        if not self.recording:
            return
        text = self._first
        self._stop()
        if text:
            self._commit_text(text)

    def _cancel(self) -> None:
        self._timer.stop()
        self._stop()
        self._edit.setText(self._armed_text)
        self._edit.setPlaceholderText("None" if not self._armed_text else "")

    def _stop(self) -> None:
        self.recording = False
        self._kick.stop()
        self._edit.setStyleSheet("")

    def _commit_text(self, text: str) -> None:
        self._edit.setText(text)
        self._edit.setPlaceholderText("None" if not text else "")
        stored = _stored(self._spec, self._previous, text)
        self._previous = stored
        self._shown = text
        self._host.commit(stored)
        self._paint_clash(text)

    def _paint_clash(self, text: str) -> None:
        if not text:
            self._warning.hide()
            self._warning.clear()
            return
        other = _clash(self._host, text)
        if not other:
            self._warning.hide()
            self._warning.clear()
            return
        self._warning.setText("%s already uses %s." % (other, text))
        self._warning.setStyleSheet("color: %s;" % warning_color(self._host.chrome))
        self._warning.show()


def _stored(spec: ValueSpec, previous: Optional[Value], text: str) -> Value:
    if spec.element == CStringValue.ELEMENT or isinstance(previous, CStringValue):
        return CStringValue(text)
    if isinstance(previous, StringValue):
        return StringValue(
            text,
            notr=previous.notr,
            comment=previous.comment,
            extracomment=previous.extracomment,
            id=previous.id,
        )
    return StringValue(text)


def _text(value: Optional[Value]) -> str:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return ""


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _action_shortcut(action: QAction) -> str:
    shortcut = action.shortcut()
    if shortcut is not None and not shortcut.isEmpty():
        return _portable(shortcut)
    # The realizer's string setter misses QAction.shortcut, so the text is
    # kept as a dynamic property on the action object.
    stored = action.property("shortcut")
    if isinstance(stored, str) and stored.strip():
        return _portable(QKeySequence.fromString(stored))
    return ""


def _actions_on(widget: QWidget) -> list:
    found = []
    actions = getattr(widget, "actions", None)
    if callable(actions):
        listed = actions()
        if isinstance(listed, (list, tuple)):
            found.extend(item for item in listed if isinstance(item, QAction))
    for child in widget.children():
        if isinstance(child, QAction) and child not in found:
            found.append(child)
    return found


def _clash(host: EditorHost, text: str) -> str:
    app = QApplication.instance()
    if app is None or not text:
        return ""
    mine = owner_name(host)
    target = _portable(QKeySequence.fromString(text))
    if not target:
        return ""
    for widget in app.allWidgets():
        if not isinstance(widget, QWidget):
            continue
        for action in _actions_on(widget):
            if mine and action.objectName() == mine:
                continue
            if _action_shortcut(action) != target:
                continue
            label = str(action.text() or "").replace("&", "").strip()
            return label or str(action.objectName())
    return ""


def register(registrar: Registrar) -> None:
    registrar.editor(KEY_SEQUENCE, KeyEditor)
