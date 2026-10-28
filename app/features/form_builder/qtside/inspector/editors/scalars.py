
from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CharValue,
    CStringValue,
    StringValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    NOT_SET_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import name_part, qt_names_visible
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QWidget

class TextEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._shown = ""
        self._edit = QLineEdit(parent)
        self._edit.editingFinished.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._edit

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        self._shown = _text_of(value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown)
        if not self._edit.hasFocus():
            # setText leaves the cursor at the end, which scrolls a long
            # value to its tail ("ame@example.com").
            self._edit.setCursorPosition(0)
        self._edit.setPlaceholderText(_placeholder(value))
        self._edit.blockSignals(False)

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        if self._spec.element == CStringValue.ELEMENT:
            self._host.commit(CStringValue(text))
            return
        self._host.commit(StringValue(text))

class BoolEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._box = QCheckBox(parent)
        self._box.setText("")
        self._box.clicked.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        mark(self._box, value)
        name_part(self._box, self._host, "value")
        self._box.blockSignals(True)
        flag = _written_bool(value)
        if isinstance(value, Mixed):
            self._box.setTristate(True)
            self._box.setCheckState(Qt.PartiallyChecked)  # type: ignore[attr-defined]
        else:
            self._box.setTristate(False)
            self._box.setChecked(bool(flag))
        self._box.blockSignals(False)

    def _commit(self, checked: bool) -> None:
        self._box.setTristate(False)
        self._host.commit(BoolValue(bool(checked)))


class CharEditor:
    """One character. A second character is refused and the file stays put."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._shown = ""
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._edit = QLineEdit(self._root)
        self._edit.setFixedWidth(32)
        self._edit.editingFinished.connect(self._commit)
        layout.addWidget(self._edit, 0)
        self._code = QLabel(self._root)
        self._code.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus"))  # type: ignore[arg-type]
        layout.addWidget(self._code, 0)
        layout.addStretch(1)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        name_part(self._edit, self._host, "character")
        text = _char_text(value)
        self._shown = text
        self._edit.blockSignals(True)
        self._edit.setText(text)
        self._edit.setPlaceholderText(MIXED_TEXT if isinstance(value, Mixed) else "")
        self._edit.blockSignals(False)
        self._paint_code(text)

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        if len(text) != 1:
            self._host.invalid("Type one character.")
            return
        self._host.commit(CharValue(unicode=ord(text)))

    def _paint_code(self, text: str) -> None:
        if len(text) == 1 and qt_names_visible(self._host):
            self._code.setText("U+%04X" % ord(text))
            self._code.setVisible(True)
            return
        self._code.clear()
        self._code.setVisible(False)


def register(registrar: Registrar) -> None:
    for element in (StringValue.ELEMENT, CStringValue.ELEMENT):
        registrar.editor(EditorKey(element), TextEditor, baseline=True)
    registrar.editor(EditorKey(BoolValue.ELEMENT), BoolEditor, baseline=True)
    registrar.editor(EditorKey(CharValue.ELEMENT), CharEditor, baseline=True)


def _char_text(value: RowValue) -> str:
    found = _written(value)
    if isinstance(found, CharValue):
        code = int(found.unicode)
        if code <= 0:
            return ""
        return chr(code)
    return ""



def _text_of(value: RowValue) -> str:
    found = _written(value)
    if isinstance(found, (StringValue, CStringValue)):
        return found.text
    return ""


def _placeholder(value: RowValue) -> str:
    if isinstance(value, Mixed):
        return MIXED_TEXT
    if isinstance(value, Unset):
        if isinstance(value.default, (StringValue, CStringValue)) and value.default.text:
            return value.default.text
        return NOT_SET_TEXT
    return ""


def _written(value: RowValue) -> Optional[Value]:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None


def _written_bool(value: RowValue) -> Optional[bool]:
    found = _written(value)
    if isinstance(found, BoolValue):
        return found.value
    return None
