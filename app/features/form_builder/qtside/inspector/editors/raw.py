
from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.reader import UiReadError, read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import IconSetValue, PaletteValue, Value
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.qtside.inspector.api import (
    STYLESHEET,
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
from app.qt.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

_PLACEHOLDER = "%%VALUE%%"
_UI = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ui version="4.0">\n'
    " <class>Holder</class>\n"
    ' <widget class="QWidget" name="Holder">\n'
    '  <widget class="QWidget" name="holder">\n'
    '   <property name="raw">\n'
    "    %%VALUE%%\n"
    "   </property>\n"
    "  </widget>\n"
    " </widget>\n"
    "</ui>\n"
)

class RawValueError(ValueError):
    pass


def raw_text(value: Optional[Value]) -> str:
    if value is None:
        return ""
    fragment = Fragment(
        nodes=(
            NodeSpec(
                kind="widget",
                fields=(("class_name", "QWidget"), ("object_name", "holder")),
                properties=(PropertyEntry("property", "raw", value),),
            ),
        )
    )
    return _cut_element(write_fragment(fragment), value.ELEMENT)

def parse_raw_value(element: str, text: str) -> Value:
    body = text.strip()
    if _opens(body, element, 0) != 0:
        raise RawValueError("expected a <%s> value" % element)
    try:
        fragment = read_fragment(_UI.replace(_PLACEHOLDER, body))
    except UiReadError as exc:
        raise RawValueError(str(exc)) from exc
    if len(fragment.nodes) != 1:
        raise RawValueError("expected one value")
    found = [entry for entry in fragment.nodes[0].properties if entry.name == "raw"]
    if len(found) != 1 or found[0].value.ELEMENT != element:
        raise RawValueError("expected a <%s> value" % element)
    return found[0].value

class RawXmlEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        self._button = QPushButton("Raw XML", self._root)
        self._button.clicked.connect(self._toggle)
        self._caption = QLabel("Raw value (XML)", self._root)
        self._box = QPlainTextEdit(self._root)
        self._apply = QPushButton("Apply", self._root)
        self._apply.clicked.connect(self._apply_text)
        layout.addWidget(self._button)
        layout.addWidget(self._caption)
        layout.addWidget(self._box)
        layout.addWidget(self._apply)
        self._caption.hide()
        self._box.hide()
        self._apply.hide()
        self._open = False

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._box, value)
        self._box.blockSignals(True)
        self._box.setPlainText(_shown_xml(value))
        self._box.blockSignals(False)

    def _toggle(self) -> None:
        self._open = not self._open
        self._caption.setVisible(self._open)
        self._box.setVisible(self._open)
        self._apply.setVisible(self._open)

    def _apply_text(self) -> None:
        try:
            parsed = parse_raw_value(self._spec.element, self._box.toPlainText())
        except RawValueError as exc:
            self._host.invalid(str(exc))
            return
        self._host.commit(parsed)

def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(PaletteValue.ELEMENT), RawXmlEditor, baseline=True)
    registrar.editor(EditorKey(IconSetValue.ELEMENT), RawXmlEditor, baseline=True)
    registrar.editor(STYLESHEET, RawXmlEditor, baseline=True)

def _shown_xml(value: RowValue) -> str:
    if isinstance(value, Written):
        return raw_text(value.value)
    if isinstance(value, Unset):
        return raw_text(value.default)
    return ""

def _opens(text: str, element: str, start: int) -> int:
    token = "<" + element
    index = text.find(token, start)
    while index >= 0:
        after = text[index + len(token) : index + len(token) + 1]
        if after in ("", ">", " ", "/", "\n", "\t", "\r"):
            return index
        index = text.find(token, index + 1)
    return -1

def _cut_element(text: str, element: str) -> str:
    start = _opens(text, element, 0)
    if start < 0:
        raise RawValueError("missing <%s>" % element)
    end_bracket = text.find(">", start)
    if end_bracket < 0:
        raise RawValueError("truncated <%s>" % element)
    if text[end_bracket - 1] == "/":
        return text[start : end_bracket + 1]
    close = "</" + element + ">"
    end = text.find(close, end_bracket)
    if end < 0:
        raise RawValueError("unclosed <%s>" % element)
    return text[start : end + len(close)]
