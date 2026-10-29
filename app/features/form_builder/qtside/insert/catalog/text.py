"""UX-CAT-002: Text and numbers, and the choice-free value widgets."""

from __future__ import annotations

from typing import Callable, Sequence, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment, PropertyEntry
from app.features.form_builder.qtside.insert.catalog._build import fragment, orientation, widget
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry, Registry

CATEGORY = "Text and numbers"


def _leaf(
    class_name: str,
    object_name: str,
    properties: Sequence[PropertyEntry] = (),
) -> Callable[[], Fragment]:
    props = tuple(properties)

    def build() -> Fragment:
        return fragment(widget(class_name, object_name, properties=props))

    return build


def _entry(
    key: str,
    friendly: str,
    qt_class: str,
    object_name: str,
    description: str,
    synonyms: Tuple[str, ...],
    glyph: str,
    properties: Sequence[PropertyEntry] = (),
    payload: str = WIDGET,
) -> Entry:
    return Entry(
        key, friendly, qt_class, CATEGORY, object_name, description, synonyms, glyph,
        payload, _leaf(qt_class, object_name, properties),
    )


def entries() -> Tuple[Entry, ...]:
    slider_synonyms = ("slider", "range", "trackbar")
    return (
        _entry("QLineEdit", "Line edit", "QLineEdit", "lineEdit",
               "One line of text the user can type.",
               ("textbox", "textfield", "input", "entry", "field", "text", "name", "password", "pin code"), "line_edit"),
        _entry("QTextEdit", "Text edit", "QTextEdit", "textEdit",
               "Several lines of text, with formatting.",
               ("richtext", "rich text", "formatted text"), "text_edit"),
        _entry("QPlainTextEdit", "Plain text edit", "QPlainTextEdit", "plainTextEdit",
               "Several lines of plain text, such as notes.",
               ("textarea", "memo", "multiline", "notes", "paragraph"), "plain_text_edit"),
        _entry("QSpinBox", "Spin box", "QSpinBox", "spinBox",
               "A whole number with up and down arrows.",
               ("number", "integer", "whole number", "counter", "numeric"), "spin_box"),
        _entry("QDoubleSpinBox", "Double spin box", "QDoubleSpinBox", "doubleSpinBox",
               "A number with decimals, such as a price.",
               ("decimal", "float", "money", "currency", "price", "amount"), "double_spin_box"),
        _entry("slider-h", "Horizontal slider", "QSlider", "horizontalSlider",
               "Pick a number by dragging a handle.", slider_synonyms, "slider_h",
               (orientation(True),)),
        _entry("slider-v", "Vertical slider", "QSlider", "verticalSlider",
               "Pick a number by dragging a handle up or down.", slider_synonyms, "slider_v",
               (orientation(False),)),
        _entry("QDial", "Dial", "QDial", "dial",
               "Pick a number by turning a knob.", ("knob",), "dial"),
        _entry("scrollbar-h", "Horizontal scroll bar", "QScrollBar", "horizontalScrollBar",
               "Scrolls something your code draws.", ("scrollbar",), "scrollbar_h",
               (orientation(True),)),
        _entry("scrollbar-v", "Vertical scroll bar", "QScrollBar", "verticalScrollBar",
               "Scrolls something your code draws.", ("scrollbar",), "scrollbar_v",
               (orientation(False),)),
        _entry("QKeySequenceEdit", "Key sequence edit", "QKeySequenceEdit", "keySequenceEdit",
               "Records a keyboard shortcut the user presses.", ("shortcut", "hotkey"), "key_sequence"),
    )


def register(registry: Registry) -> None:
    registry.family("QSlider", "Slider")
    registry.family("QScrollBar", "Scroll bar")
    for entry in entries():
        registry.add(entry)
