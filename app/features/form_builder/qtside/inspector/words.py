
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.qt_signals import signal_names
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.insert.catalog import load_catalog

@dataclass(frozen=True)
class ClassWords:
    friendly: str
    plural: str
    noun: str
    glyph: str


# The friendly name comes from the Insert catalog (UX-CAT-001). These extras are the
# plural, noun and inspector glyph that the catalog does not carry.
_EXTRAS: Mapping[str, Tuple[str, str, str]] = {
    "QWidget": ("widgets", "widget", "widget"),
    "QDialog": ("dialogs", "dialog", "window"),
    "QMainWindow": ("main windows", "window", "window"),
    "QPushButton": ("push buttons", "button", "button"),
    "QToolButton": ("tool buttons", "button", "button"),
    "QCommandLinkButton": ("command links", "button", "button"),
    "QCheckBox": ("check boxes", "check box", "checkbox"),
    "QRadioButton": ("radio buttons", "radio button", "radio"),
    "QLineEdit": ("line edits", "field", "field"),
    "QTextEdit": ("text edits", "text box", "textbox"),
    "QPlainTextEdit": ("plain text edits", "text box", "textbox"),
    "QLabel": ("labels", "label", "label"),
    "QComboBox": ("combo boxes", "combo box", "combo"),
    "QSpinBox": ("spin boxes", "spin box", "number"),
    "QDoubleSpinBox": ("double spin boxes", "spin box", "number"),
    "QSlider": ("sliders", "slider", "slider"),
    "QDial": ("dials", "dial", "slider"),
    "QDateEdit": ("date edits", "date field", "date"),
    "QTimeEdit": ("time edits", "time field", "date"),
    "QDateTimeEdit": ("date and time edits", "date field", "date"),
    "QGroupBox": ("group boxes", "group box", "group"),
    "QFrame": ("frames", "frame", "group"),
    "QTabWidget": ("tab widgets", "tab widget", "tabs"),
    "QStackedWidget": ("stacked widgets", "stack", "tabs"),
    "QScrollArea": ("scroll areas", "scroll area", "group"),
    "QListWidget": ("list widgets", "list", "list"),
    "QTableWidget": ("table widgets", "table", "table"),
    "QTableView": ("table views", "table", "table"),
    "QTreeWidget": ("tree widgets", "tree", "tree"),
    "QTreeView": ("tree views", "tree", "tree"),
    "QDialogButtonBox": ("button boxes", "button box", "button"),
    "QProgressBar": ("progress bars", "progress bar", "progress"),
    "QVBoxLayout": ("vertical layouts", "layout", "layout"),
    "QHBoxLayout": ("horizontal layouts", "layout", "layout"),
    "QGridLayout": ("grid layouts", "layout", "layout"),
    "QFormLayout": ("form layouts", "layout", "layout"),
}

_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def _plural_of(noun: str) -> str:
    return noun + ("es" if noun.endswith(("s", "x", "ch", "sh")) else "s")


def class_words(qt_class: str) -> ClassWords:
    """Friendly name from the catalog, else derived from the class name (UX-CAT-001)."""
    friendly = load_catalog().friendly_for_class(qt_class)
    extras = _EXTRAS.get(qt_class)
    if friendly is None:
        bare = qt_class[1:] if qt_class[:1] == "Q" and qt_class[1:2].isupper() else qt_class
        parts = [part.lower() for part in _CAMEL.findall(bare)] or [qt_class.lower()]
        noun = " ".join(parts)
        friendly = noun[:1].upper() + noun[1:]
        if extras is None:
            return ClassWords(friendly, _plural_of(noun), noun, "widget")
    if extras is None:
        noun = friendly.lower()
        return ClassWords(friendly, _plural_of(noun), noun, "widget")
    plural, noun, glyph = extras
    return ClassWords(friendly, plural, noun, glyph)


@dataclass(frozen=True)
class EventWords:

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
    return signature.split("(", 1)[0].strip()

def event_words(signature: str) -> EventWords:
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
