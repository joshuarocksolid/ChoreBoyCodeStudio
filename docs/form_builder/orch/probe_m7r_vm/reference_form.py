"""Deterministic reference forms for the speed harness.

``reference_form`` is a pure function of ``(widget_count, seed)``. The same
pair always returns the same ``.ui`` text. The seed changes tooltip text only.
The widget tree, classes and property kinds are a function of the count, so a
300-widget form is the same shape as a 1000-widget form with fewer fields.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

DEFAULT_SEED = 1505
REFERENCE_COUNTS: Tuple[int, ...] = (300, 600, 1000)
EDIT_NAME = "field0000"

# Root, central widget, banner, tab widget, two pages, splitter, group box,
# grid pane, menu bar, menu, toolbar, status bar. One more leaf is required
# so the edit target ``field0000`` exists.
_CHROME_WIDGETS = 13
_MINIMUM_WIDGETS = _CHROME_WIDGETS + 1

_FIELD_CLASSES: Tuple[str, ...] = (
    "QLineEdit",
    "QComboBox",
    "QSpinBox",
    "QCheckBox",
    "QDateEdit",
    "QDoubleSpinBox",
    "QSlider",
    "QRadioButton",
    "QTextEdit",
    "QPushButton",
)
_CAPTIONS: Tuple[str, ...] = (
    "Customer",
    "Route",
    "Quantity",
    "Due",
    "Tax",
    "SKU",
    "Notes",
    "Phone",
    "Email",
    "City",
)
_TIPS: Tuple[str, ...] = (
    "customer",
    "invoice",
    "route",
    "quantity",
    "notes",
    "due",
    "tax",
    "sku",
)


@dataclass(frozen=True)
class ReferenceForm:
    """One generated ``.ui`` document."""

    widget_count: int
    seed: int
    xml: str
    edit_name: str


def reference_form(widget_count: int, seed: int = DEFAULT_SEED) -> ReferenceForm:
    """Build a main-window form with exactly ``widget_count`` ``<widget>`` tags."""
    if widget_count < _MINIMUM_WIDGETS:
        raise ValueError(
            "reference form needs at least %d widgets, got %d"
            % (_MINIMUM_WIDGETS, widget_count)
        )
    rng = random.Random(seed)
    form_count, grid_count, notes_count = _split_leaves(widget_count - _CHROME_WIDGETS)
    field_index = 0
    parts: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ui version="4.0">',
        "<class>OrderWindow</class>",
        '<widget class="QMainWindow" name="OrderWindow">',
        _property_rect("geometry", 0, 0, 960, 640),
        _property_string("windowTitle", "Order %d" % widget_count),
        '<widget class="QWidget" name="central">',
        '<layout class="QVBoxLayout" name="outer">',
        "<item>",
        '<layout class="QHBoxLayout" name="headerBar">',
        "<item>",
        _widget(
            "QLabel",
            "banner",
            (
                _property_string("text", "Orders"),
                _property_string("toolTip", _tip(rng, 0)),
            ),
        ),
        "</item>",
        "</layout>",
        "</item>",
        "<item>",
        '<widget class="QTabWidget" name="tabs">',
        _property_number("currentIndex", 0),
        '<widget class="QWidget" name="tabDetails">',
        '<attribute name="title"><string>Details</string></attribute>',
        '<widget class="QSplitter" name="split">',
        _property_enum("orientation", "Qt::Horizontal"),
        '<widget class="QGroupBox" name="identity">',
        _property_string("title", "Identity"),
        '<layout class="QFormLayout" name="identityForm">',
    ]
    for row in range(form_count // 2):
        label_name = "label%04d" % field_index
        field_name = "field%04d" % field_index
        field_class = _FIELD_CLASSES[field_index % len(_FIELD_CLASSES)]
        parts.append('<item row="%d" column="0">' % row)
        parts.append(
            _widget(
                "QLabel",
                label_name,
                (
                    _property_string("text", _CAPTIONS[field_index % len(_CAPTIONS)]),
                    _property_string("buddy", None, cstring=field_name),
                    _property_string("toolTip", _tip(rng, field_index)),
                ),
            )
        )
        parts.append("</item>")
        parts.append('<item row="%d" column="1">' % row)
        parts.append(_field_widget(field_class, field_name, field_index, rng))
        parts.append("</item>")
        field_index += 1
    parts.extend(
        [
            "</layout>",
            "</widget>",
            '<widget class="QWidget" name="gridPane">',
            '<layout class="QGridLayout" name="grid">',
        ]
    )
    for offset in range(grid_count):
        field_name = "field%04d" % field_index
        field_class = _FIELD_CLASSES[field_index % len(_FIELD_CLASSES)]
        row, column = divmod(offset, 4)
        parts.append('<item row="%d" column="%d">' % (row, column))
        parts.append(_field_widget(field_class, field_name, field_index, rng))
        parts.append("</item>")
        field_index += 1
    parts.extend(
        [
            "</layout>",
            "</widget>",
            "</widget>",
            "</widget>",
            '<widget class="QWidget" name="tabNotes">',
            '<attribute name="title"><string>Notes</string></attribute>',
            '<layout class="QGridLayout" name="notesGrid">',
        ]
    )
    for offset in range(notes_count):
        field_name = "field%04d" % field_index
        field_class = _FIELD_CLASSES[field_index % len(_FIELD_CLASSES)]
        row, column = divmod(offset, 4)
        parts.append('<item row="%d" column="%d">' % (row, column))
        parts.append(_field_widget(field_class, field_name, field_index, rng))
        parts.append("</item>")
        field_index += 1
    parts.extend(
        [
            "</layout>",
            "</widget>",
            "</widget>",
            "</item>",
            "</layout>",
            "</widget>",
            '<widget class="QMenuBar" name="menuBar">',
            '<widget class="QMenu" name="menuFile">',
            _property_string("title", "File"),
            '<addaction name="actionNew"/>',
            '<addaction name="separator"/>',
            '<addaction name="actionSave"/>',
            '<addaction name="actionClose"/>',
            "</widget>",
            '<addaction name="menuFile"/>',
            "</widget>",
            '<widget class="QToolBar" name="toolBar">',
            _property_string("windowTitle", "Main"),
            '<addaction name="actionNew"/>',
            '<addaction name="actionSave"/>',
            '<addaction name="actionRefresh"/>',
            "</widget>",
            '<widget class="QStatusBar" name="statusBar"/>',
            '<action name="actionNew">' + _property_string("text", "New") + "</action>",
            '<action name="actionSave">' + _property_string("text", "Save") + "</action>",
            '<action name="actionRefresh">' + _property_string("text", "Refresh") + "</action>",
            '<action name="actionClose">' + _property_string("text", "Close") + "</action>",
            '<addaction name="actionNew"/>',
            "</widget>",
            "<resources/>",
            "<connections/>",
            "</ui>",
            "",
        ]
    )
    if field_index < 1:
        raise ValueError("reference form has no editable field")
    xml = "\n".join(parts)
    return ReferenceForm(widget_count, seed, xml, EDIT_NAME)


def _split_leaves(leaves: int) -> Tuple[int, int, int]:
    """Form rows consume labels and fields in pairs. Grid and notes take the rest."""
    form = (leaves * 2 // 5) // 2 * 2
    grid = leaves * 2 // 5
    notes = leaves - form - grid
    return form, grid, notes


def _tip(rng: random.Random, index: int) -> str:
    return "%s %d" % (rng.choice(_TIPS), index)


def _field_widget(class_name: str, name: str, index: int, rng: random.Random) -> str:
    props: List[str] = [_property_string("toolTip", _tip(rng, index))]
    if class_name in ("QLineEdit", "QPushButton", "QRadioButton", "QTextEdit"):
        props.append(_property_string("text", _CAPTIONS[index % len(_CAPTIONS)]))
    if class_name == "QLineEdit":
        props.append(_property_number("maxLength", 32 + (index % 16)))
    if class_name == "QCheckBox":
        props.append(_property_string("text", _CAPTIONS[index % len(_CAPTIONS)]))
        props.append(_property_bool("checked", index % 2 == 0))
    if index % 4 == 0:
        props.append(_property_size("minimumSize", 10, 20))
    if index % 5 == 0:
        props.append(_property_font())
    if index % 7 == 0:
        props.append(_property_bool("enabled", False))
    return _widget(class_name, name, tuple(props))


def _widget(class_name: str, name: str, properties: Sequence[str]) -> str:
    if not properties:
        return '<widget class="%s" name="%s"/>' % (class_name, name)
    return '<widget class="%s" name="%s">\n%s\n</widget>' % (
        class_name,
        name,
        "\n".join(properties),
    )


def _property_string(name: str, text: Optional[str] = None, cstring: str = "") -> str:
    if cstring:
        return '<property name="%s"><cstring>%s</cstring></property>' % (name, escape(cstring))
    return '<property name="%s"><string>%s</string></property>' % (name, escape(text or ""))


def _property_number(name: str, value: int) -> str:
    return '<property name="%s"><number>%d</number></property>' % (name, value)


def _property_bool(name: str, value: bool) -> str:
    return '<property name="%s"><bool>%s</bool></property>' % (name, "true" if value else "false")


def _property_enum(name: str, value: str) -> str:
    return '<property name="%s"><enum>%s</enum></property>' % (name, value)


def _property_rect(name: str, x: int, y: int, width: int, height: int) -> str:
    return (
        '<property name="%s"><rect><x>%d</x><y>%d</y><width>%d</width><height>%d</height></rect></property>'
        % (name, x, y, width, height)
    )


def _property_size(name: str, width: int, height: int) -> str:
    return (
        '<property name="%s"><size><width>%d</width><height>%d</height></size></property>'
        % (name, width, height)
    )


def _property_font() -> str:
    return (
        '<property name="font"><font><family>Sans</family><pointsize>10</pointsize>'
        "<bold>true</bold></font></property>"
    )
