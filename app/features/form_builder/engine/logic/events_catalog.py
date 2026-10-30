"""The events catalog: common and default events per class, and the words (UX-PICK-002, UX 13.3.8). Qt-free.

One table feeds the event picker, the Events list, docstrings and method
names. It is LOGIC_DESIGN 2.2 without pseudo-events and form events (UX D16).
A class not listed here uses its nearest listed base class; an own class
(promoted, UX-CUST-006) uses its base class's row plus the signals its
``<customwidget><slots>`` declares. Nothing here reads project code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.compat import split_signature
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.ui4.defaults import QtClassTable


@dataclass(frozen=True)
class EventWords:
    """``header``: "When {header}" and picker items; ``doc``: "Runs when {object} is {doc}.";
    ``short``: the method-name word (UX-CODE-001). ``clause`` is a complete English
    clause after "When", with ``{display}`` and ``{signal}`` (D27)."""

    header: str
    doc: str
    short: str
    clause: str = "{display} sends {signal}"


@dataclass(frozen=True)
class ClassEvents:
    """Common events of a class, in picker order, and the one a double-click means."""

    common: Tuple[str, ...]
    default: Optional[str]


def snake_case(name: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return spaced.lower()


_BY_SIGNAL: Dict[str, EventWords] = {
    "clicked": EventWords("clicked", "clicked", "clicked", "{display} is clicked"),
    "pressed": EventWords("pressed", "pressed", "pressed", "{display} is pressed"),
    "released": EventWords("released", "released", "released", "{display} is released"),
    "toggled": EventWords("checked or unchecked", "checked or unchecked", "toggled", "{display} is checked or unchecked"),
    "editingFinished": EventWords("editing is finished", "finished editing", "done", "you finish editing {display}"),
    "returnPressed": EventWords("Enter is pressed", "given Enter", "enter", "Enter is pressed in {display}"),
    "textChanged": EventWords("the text changes", "changed", "text_changed", "the text of {display} changes"),
    "textEdited": EventWords("the text is typed", "changed", "typed", "the text is typed in {display}"),
    "currentIndexChanged": EventWords("the choice changes", "changed", "changed", "the choice of {display} changes"),
    "valueChanged": EventWords("the value changes", "changed", "changed", "the value of {display} changes"),
    "dateChanged": EventWords("the date changes", "changed", "changed", "the date of {display} changes"),
    "timeChanged": EventWords("the time changes", "changed", "changed", "the time of {display} changes"),
    "dateTimeChanged": EventWords("the date or time changes", "changed", "changed", "the date or time of {display} changes"),
    "itemActivated": EventWords("an item is opened", "opened", "opened", "an item in {display} is opened"),
    "currentRowChanged": EventWords("another row is chosen", "moved to another row", "row_changed", "the row of {display} changes"),
    "accepted": EventWords("OK is pressed", "accepted", "ok", "OK is pressed in {display}"),
    "rejected": EventWords("Cancel is pressed", "cancelled", "cancel", "Cancel is pressed in {display}"),
    "triggered": EventWords("chosen", "chosen", "triggered", "{display} is chosen"),
    "finished": EventWords("it closes", "closed", "closed", "{display} closes"),
}

#: Words that depend on the class the signal belongs to: (signal, class in the chain).
_BY_CLASS: Dict[Tuple[str, str], EventWords] = {
    ("clicked", "QDialogButtonBox"): EventWords(
        "any of its buttons is clicked", "clicked", "button_clicked", "a button in {display} is clicked"
    ),
    ("activated", "QComboBox"): EventWords("a choice is picked", "picked", "picked", "a choice is picked in {display}"),
    ("currentChanged", "QTabWidget"): EventWords(
        "the page changes", "switched to another page", "page_changed", "the page of {display} changes"
    ),
    ("currentChanged", "QStackedWidget"): EventWords(
        "the page changes", "switched to another page", "page_changed", "the page of {display} changes"
    ),
    ("currentChanged", "QToolBox"): EventWords(
        "the page changes", "switched to another page", "page_changed", "the page of {display} changes"
    ),
}


def event_words(signal_name: str, chain: Sequence[str] = ()) -> EventWords:
    """The words of an event. ``chain`` is the sender's class and its bases, leaf first.

    An event the table has no words for reads as the signal name as Qt writes it.
    """
    for class_name in chain:
        found = _BY_CLASS.get((signal_name, class_name))
        if found is not None:
            return found
    if signal_name == "activated":
        return EventWords("activated", "activated", "activated", "{display} is activated")
    found = _BY_SIGNAL.get(signal_name)
    if found is not None:
        return found
    return EventWords(signal_name, signal_name, snake_case(signal_name))


def event_clause(signal_name: str, chain: Sequence[str], display: str) -> str:
    """The clause that follows "When". Headers stay on ``event_words().header``."""
    words = event_words(signal_name, chain)
    return words.clause.format(display=display, signal=signal_name)


def catalog_signals() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """Every named row, as (signal, class chain), for the clause test."""
    rows = [(name, ()) for name in _BY_SIGNAL]
    rows.append(("activated", ()))
    for signal, class_name in _BY_CLASS:
        rows.append((signal, (class_name,)))
    return tuple(rows)


_BUTTONS = ClassEvents(("clicked",), "clicked")
_SPIN = ClassEvents(("valueChanged", "editingFinished"), "valueChanged")
_SLIDER = ClassEvents(("valueChanged",), "valueChanged")

_CLASS_EVENTS: Dict[str, ClassEvents] = {
    "QPushButton": _BUTTONS,
    "QToolButton": _BUTTONS,
    "QCheckBox": ClassEvents(("toggled", "clicked"), "toggled"),
    "QRadioButton": ClassEvents(("toggled", "clicked"), "toggled"),
    "QLineEdit": ClassEvents(("editingFinished", "returnPressed", "textChanged"), "editingFinished"),
    "QPlainTextEdit": ClassEvents(("textChanged",), "textChanged"),
    "QTextEdit": ClassEvents(("textChanged",), "textChanged"),
    "QComboBox": ClassEvents(("currentIndexChanged", "activated"), "currentIndexChanged"),
    "QSpinBox": _SPIN,
    "QDoubleSpinBox": _SPIN,
    "QSlider": _SLIDER,
    "QDial": _SLIDER,
    "QDateEdit": ClassEvents(("dateChanged",), "dateChanged"),
    "QTimeEdit": ClassEvents(("timeChanged",), "timeChanged"),
    "QDateTimeEdit": ClassEvents(("dateTimeChanged",), "dateTimeChanged"),
    "QTabWidget": ClassEvents(("currentChanged",), "currentChanged"),
    "QListWidget": ClassEvents(("itemActivated", "currentRowChanged"), "itemActivated"),
    "QTableView": ClassEvents(("activated",), "activated"),
    "QTreeView": ClassEvents(("activated",), "activated"),
    "QDialogButtonBox": ClassEvents(("accepted", "rejected", "clicked"), "accepted"),
    "QAction": ClassEvents(("triggered",), "triggered"),
    # The root of a dialog: its real signals only (UX D16); a double-click means none of them.
    "QDialog": ClassEvents(("accepted", "rejected", "finished"), None),
}


def class_events(classes: QtClassTable, class_name: str) -> Optional[ClassEvents]:
    """The row of ``class_name`` or its nearest listed base, or None."""
    for info in classes.chain(class_name):
        found = _CLASS_EVENTS.get(info.name)
        if found is not None:
            return found
    return _CLASS_EVENTS.get(class_name)


def common_events(
    classes: QtClassTable, class_name: str, declared_signals: Sequence[str] = ()
) -> Tuple[str, ...]:
    """Signal names for the COMMON section, in order. An own class adds its declared signals after its base's."""
    row = class_events(classes, class_name)
    names = list(row.common) if row is not None else []
    for signature in declared_signals:
        name = split_signature(signature)[0]
        if name and name not in names:
            names.append(name)
    return tuple(names)


def default_event(classes: QtClassTable, class_name: str) -> Optional[str]:
    """The event a double-click on the class means (``None`` when it has none)."""
    row = class_events(classes, class_name)
    return row.default if row is not None else None


def class_chain(classes: QtClassTable, class_name: str) -> Tuple[str, ...]:
    return tuple(info.name for info in classes.chain(class_name))


def more_events(classes: QtClassTable, class_name: str, declared_signals: Sequence[str] = ()) -> Tuple[str, ...]:
    """Every other signal name of the class chain below ``QWidget``, alphabetical (UX-PICK-001)."""
    common = set(common_events(classes, class_name, declared_signals))
    names = set()
    for info in classes.chain(class_name):
        if info.name in ("QWidget", "QObject"):
            break
        for signature in _own_signals(classes, info.name):
            names.add(split_signature(signature)[0])
    for signature in declared_signals:
        names.add(split_signature(signature)[0])
    return tuple(sorted(names - common))


def _own_signals(classes: QtClassTable, class_name: str) -> Tuple[str, ...]:
    all_here = classes.signals(class_name)
    parent = classes.class_info(class_name)
    if parent is None or parent.super_name is None:
        return all_here
    inherited = set(classes.signals(parent.super_name))
    return tuple(item for item in all_here if item not in inherited)


# --- value words (UX 13.3.8 "Value words") ---------------------------------------------

_VALUE_WORDS = {
    "bool": "whether it's checked",
    "QString": "the new text",
    "int": "the new number",
    "double": "the new number",
    "QDate": "the new date",
    "QTime": "the new time",
    "QDateTime": "the new date and time",
    "QAbstractButton*": "the button that was clicked",
}


def value_words(type_name: str, signal_name: str = "", chain: Sequence[str] = ()) -> str:
    """"My method receives {words}" for the first value of a signal."""
    if type_name == "int":
        if signal_name in ("currentIndexChanged", "activated", "currentChanged"):
            if "QTabWidget" in chain or "QStackedWidget" in chain or "QToolBox" in chain:
                return "the number of the new page"
            return "the number of the new choice"
    return _VALUE_WORDS.get(type_name, "the new value")


# --- step words (UX-BEH-004) ------------------------------------------------------------

_FORM_WORDS = {"close": "Close this form", "accept": "Accept (OK)", "reject": "Cancel"}

_PLAIN_SLOT_WORDS = {
    "clear": "Clear {w}",
    "setFocus": "Move focus to {w}",
    "setChecked": "Check or uncheck {w} the same way",
    "toggle": "Toggle {w}",
    "click": "Click {w}",
    "setValue": "Set {w} to the same value",
    "setEnabled": "Enable {w} to match",
    "setDisabled": "Disable {w} to match",
    "setVisible": "Show {w} to match",
    "show": "Show {w}",
    "hide": "Hide {w}",
    "setText": "Copy the text into {w}",
    "selectAll": "Select all in {w}",
    "undo": "Undo in {w}",
    "redo": "Redo in {w}",
    "copy": "Copy in {w}",
    "paste": "Paste in {w}",
    "cut": "Cut in {w}",
    "update": "Redraw {w}",
    "repaint": "Redraw {w}",
    "raise": "Bring {w} to the front",
    "lower": "Send {w} to the back",
}


def step_words(
    step: EventStep,
    w: str,
    *,
    is_form: bool = False,
    target_chain: Sequence[str] = (),
) -> str:
    """A step as a sentence. ``w`` is the target as the caller names it ("Name (nameEdit)")."""
    if step.verb == "call":
        return "Call %s()" % step.method
    if step.verb != "slot":
        return "A step Code Studio can't edit (%s)" % step.verb
    name = split_signature(step.slot)[0]
    if is_form and name in _FORM_WORDS:
        return _FORM_WORDS[name]
    if name == "setCurrentIndex":
        if "QComboBox" in target_chain:
            return "Choose the matching item of %s" % w
        return "Show the matching page of %s" % w
    template = _PLAIN_SLOT_WORDS.get(name)
    if template is not None:
        return template.replace("{w}", w)
    return "%s · %s" % (w, name)
