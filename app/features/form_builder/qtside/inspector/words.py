"""The English the inspector speaks about Qt classes and signals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from app.features.form_builder.engine.codegen.qt_signals import signal_names
from app.features.form_builder.engine.ui4.defaults import QtClassTable


@dataclass(frozen=True)
class ClassWords:
    friendly: str
    plural: str
    noun: str
    glyph: str


_CLASS_WORDS: Mapping[str, ClassWords] = {
    "QWidget": ClassWords("Widget", "widgets", "widget", "widget"),
    "QDialog": ClassWords("Dialog", "dialogs", "dialog", "window"),
    "QMainWindow": ClassWords("Main window", "main windows", "window", "window"),
    "QPushButton": ClassWords("Push button", "push buttons", "button", "button"),
    "QToolButton": ClassWords("Tool button", "tool buttons", "button", "button"),
    "QCommandLinkButton": ClassWords("Command link", "command links", "button", "button"),
    "QCheckBox": ClassWords("Check box", "check boxes", "check box", "checkbox"),
    "QRadioButton": ClassWords("Radio button", "radio buttons", "radio button", "radio"),
    "QLineEdit": ClassWords("Line edit", "line edits", "field", "field"),
    "QTextEdit": ClassWords("Text edit", "text edits", "text box", "textbox"),
    "QPlainTextEdit": ClassWords("Plain text edit", "plain text edits", "text box", "textbox"),
    "QLabel": ClassWords("Label", "labels", "label", "label"),
    "QComboBox": ClassWords("Combo box", "combo boxes", "combo box", "combo"),
    "QSpinBox": ClassWords("Spin box", "spin boxes", "spin box", "number"),
    "QDoubleSpinBox": ClassWords("Double spin box", "double spin boxes", "spin box", "number"),
    "QSlider": ClassWords("Slider", "sliders", "slider", "slider"),
    "QDial": ClassWords("Dial", "dials", "dial", "slider"),
    "QDateEdit": ClassWords("Date edit", "date edits", "date field", "date"),
    "QTimeEdit": ClassWords("Time edit", "time edits", "time field", "date"),
    "QDateTimeEdit": ClassWords("Date and time edit", "date and time edits", "date field", "date"),
    "QGroupBox": ClassWords("Group box", "group boxes", "group box", "group"),
    "QFrame": ClassWords("Frame", "frames", "frame", "group"),
    "QTabWidget": ClassWords("Tab widget", "tab widgets", "tab widget", "tabs"),
    "QStackedWidget": ClassWords("Stacked widget", "stacked widgets", "stack", "tabs"),
    "QScrollArea": ClassWords("Scroll area", "scroll areas", "scroll area", "group"),
    "QListWidget": ClassWords("List widget", "list widgets", "list", "list"),
    "QTableWidget": ClassWords("Table widget", "table widgets", "table", "table"),
    "QTableView": ClassWords("Table view", "table views", "table", "table"),
    "QTreeWidget": ClassWords("Tree widget", "tree widgets", "tree", "tree"),
    "QTreeView": ClassWords("Tree view", "tree views", "tree", "tree"),
    "QDialogButtonBox": ClassWords("Button box", "button boxes", "button box", "button"),
    "QProgressBar": ClassWords("Progress bar", "progress bars", "progress bar", "progress"),
    "QVBoxLayout": ClassWords("Vertical layout", "vertical layouts", "layout", "layout"),
    "QHBoxLayout": ClassWords("Horizontal layout", "horizontal layouts", "layout", "layout"),
    "QGridLayout": ClassWords("Grid layout", "grid layouts", "layout", "layout"),
    "QFormLayout": ClassWords("Form layout", "form layouts", "layout", "layout"),
}

_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def class_words(qt_class: str) -> ClassWords:
    """Known classes come from one table. Unknown ones derive words from the class name."""
    known = _CLASS_WORDS.get(qt_class)
    if known is not None:
        return known
    bare = qt_class[1:] if qt_class[:1] == "Q" and qt_class[1:2].isupper() else qt_class
    parts = [part.lower() for part in _CAMEL.findall(bare)] or [qt_class.lower()]
    noun = " ".join(parts)
    plural = noun + ("es" if noun.endswith(("s", "x", "ch", "sh")) else "s")
    return ClassWords(noun[:1].upper() + noun[1:], plural, noun, "widget")


@dataclass(frozen=True)
class EventWords:
    """``short`` reads after "When". ``clause`` completes "Nothing happens yet when ..."."""

    short: str
    clause: str


_EVENT_WORDS: Mapping[str, EventWords] = {
    "clicked": EventWords("clicked", "this {noun} is clicked"),
    "pressed": EventWords("pressed and held", "this {noun} is pressed and held"),
    "released": EventWords("released", "this {noun} is released"),
    "toggled": EventWords("checked or unchecked", "this {noun} is checked or unchecked"),
    "editingFinished": EventWords("editing finished", "editing of this {noun} is finished"),
    "returnPressed": EventWords("Enter pressed", "Enter is pressed in this {noun}"),
    "textChanged": EventWords("text changed", "the text of this {noun} changes"),
    "currentIndexChanged": EventWords("choice changed", "the choice in this {noun} changes"),
    "activated": EventWords("activated", "this {noun} is activated"),
    "valueChanged": EventWords("value changed", "the value of this {noun} changes"),
    "dateChanged": EventWords("date changed", "the date in this {noun} changes"),
    "timeChanged": EventWords("time changed", "the time in this {noun} changes"),
    "dateTimeChanged": EventWords("date and time changed", "the date or time in this {noun} changes"),
    "currentChanged": EventWords("tab changed", "the current tab of this {noun} changes"),
    "itemActivated": EventWords("item activated", "an item in this {noun} is activated"),
    "currentRowChanged": EventWords("selection changed", "the selected row of this {noun} changes"),
    "accepted": EventWords("OK or Save", "OK or Save is pressed in this {noun}"),
    "rejected": EventWords("Cancel", "Cancel is pressed in this {noun}"),
    "triggered": EventWords("triggered", "this {noun} is triggered"),
}


def signal_name(signature: str) -> str:
    """``textChanged(QString)`` gives ``textChanged``."""
    return signature.split("(", 1)[0].strip()


def event_words(signature: str) -> EventWords:
    """The phrases for a signal. Signals outside the table read as their split name."""
    name = signal_name(signature)
    known = _EVENT_WORDS.get(name)
    if known is not None:
        return known
    spoken = " ".join(part.lower() for part in _CAMEL.findall(name)) or name
    return EventWords(spoken, "this {noun} sends " + name)


_DEFAULT_SIGNALS: Mapping[str, str] = {
    "QCheckBox": "toggled(bool)",
    "QRadioButton": "toggled(bool)",
    "QAbstractButton": "clicked()",
    "QLineEdit": "editingFinished()",
    "QPlainTextEdit": "textChanged()",
    "QTextEdit": "textChanged()",
    "QComboBox": "currentIndexChanged(int)",
    "QDoubleSpinBox": "valueChanged(double)",
    "QSpinBox": "valueChanged(int)",
    "QAbstractSlider": "valueChanged(int)",
    "QTimeEdit": "timeChanged(QTime)",
    "QDateTimeEdit": "dateChanged(QDate)",
    "QTabWidget": "currentChanged(int)",
    "QListWidget": "itemActivated(QListWidgetItem*)",
    "QAbstractItemView": "activated(QModelIndex)",
    "QDialogButtonBox": "accepted()",
    "QAction": "triggered()",
}


def default_signal(chain: Sequence[str], classes: QtClassTable) -> Optional[str]:
    """The signal a new connection starts from, as a signature, or None.

    ClassInfo.default_signal wins for the first class in ``chain`` that has one.
    Otherwise the LOGIC_DESIGN 2.2 table is read leaf first. A signal is kept
    only when ``signal_names(chain[0])`` lists it, or when that class is unknown.
    """
    if not chain:
        return None
    found: Optional[str] = None
    for qt_class in chain:
        info = classes.class_info(qt_class)
        if info is not None and info.default_signal:
            found = info.default_signal
            break
    if found is None:
        found = next((_DEFAULT_SIGNALS[name] for name in chain if name in _DEFAULT_SIGNALS), None)
    if found is None:
        return None
    known = signal_names(chain[0])
    if known is not None and signal_name(found) not in known:
        return None
    return found
