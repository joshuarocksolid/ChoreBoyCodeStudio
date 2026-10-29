# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The style sheet check agrees with Qt's own parser, and the selector matcher with Qt's own styling."""

from __future__ import annotations

from typing import List

import pytest

from app.features.form_builder.engine.style.check import QT_CANT_READ, check_sheet
from app.features.form_builder.engine.style.properties import KNOWN_PROPERTIES
from app.features.form_builder.engine.style.selectors import StyleIndex, match_sheet
from app.features.form_builder.engine.style.sheet import parse_sheet
from app.features.form_builder.qtside.style.probe import ask_qt, qt_reads
from app.qt.QtCore import qInstallMessageHandler
from app.qt.QtWidgets import QApplication, QLabel
from tests.form_builder.qtside.support import opened

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

#: Text the shape of which Qt refuses. The engine must say so too, with a place.
_QT_REFUSES = [
    "QPushButton { color: red;",
    "QPushButton { color: red; } }",
    "}",
    "QPushButton { color: red; } {",
    "QPushButton { color: red; } QLabel {",
    "QPushButton[ { color: red; }",
    "QPushButton[text { color: red; }",
    "QPushButton] { color: red; }",
    "QPushButton { color: red); }",
    "QPushButton { color: rgb(1,2,3; }",
    "QPushButton { color: rgb(1,2,3)); }",
    "QPushButton { color: [red; }",
    "QPushButton { color: red]; }",
    'QPushButton { color: "red; }',
    'QLabel { color: "a\nb"; }',
    "QLabel { color: red; ] }",
    "QLabel { ( color: red; }",
    "QLabel { image: url(; }",
    "QLabel { color: red; }}",
    "color: red; }",
    "QPushButton color: red; }",
    "QPushButton { color: red; /* c",
    "QLabel { color: red; } /* x */ }",
]

#: Text Qt refuses for a reason this check does not model. Qt's verdict says so, with no line.
_QT_ONLY = [", QPushButton { color: red; }", "> QPushButton { color: red; }", "~ QLabel { }", ":", "{}", "QLabel:not(.x) { color: red }"]

#: Text Qt reads. Findings, if any, are warnings and the sheet applies.
_QT_READS = [
    "",
    "color: red;",
    "color: red",
    "QPushButton { color: red }",
    "QPushButton { color: red; }",
    "QPushButton { color: red; /* c } */ }",
    "QPushButton { color: red; /* c }",
    "QPushButton { color red; }",
    "QPushButton { colr: red; }",
    "QPushButton { color: red background: blue; }",
    "QPushButton { color: red; background: blue }",
    "QPushButton:hovr { color: red; }",
    "QPushButton::foo { color: red; }",
    "QPushButton { color: red;; }",
    "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 red, stop:1 blue); }",
    'QPushButton[text="a"] { color:red; }',
    "#ok > QLabel, QLabel { color: red; }",
    "color: red; QLabel { color: blue; }",
    'QPushButton { font: bold 12pt "Sans Serif"; }',
    "QLabel { image: url(:/pictures/a.png); }",
    'QLabel { image: url("a;b"); }',
    "@import 'a.css'; QLabel { color: red; }",
    "QPushButton { color: red; } QLabel",
    "QLabel { color: red; }\n/* two\nlines */\nQPushButton { color: blue; }\n",
]


def test_the_engine_refuses_exactly_what_qt_refuses_on_the_corpus() -> None:
    for text in _QT_REFUSES:
        assert qt_reads(text) is False, text
        found = parse_sheet(text)
        assert found.errors(), text
        checked = check_sheet(text, qt_readable=False)
        assert checked.status == "error" and checked.line >= 1 and checked.message != QT_CANT_READ, text
    for text in _QT_READS:
        assert qt_reads(text) is True, text
        assert not parse_sheet(text).errors(), text
        assert check_sheet(text, qt_readable=True).applies, text


def test_what_the_engine_cannot_see_is_left_to_qt_without_a_line() -> None:
    for text in _QT_ONLY:
        assert qt_reads(text) is False, text
        assert not parse_sheet(text).errors(), text
        checked = check_sheet(text, qt_readable=False)
        assert (checked.status, checked.message, checked.line) == ("error", QT_CANT_READ, 0), text


def test_the_property_list_is_what_qt_knows() -> None:
    def unknown(names: List[str]) -> List[str]:
        seen: List[str] = []
        previous = qInstallMessageHandler(lambda mode, context, message: seen.append(message))
        try:
            label = QLabel("x")
            label.setStyleSheet("".join("* { %s: 1px; }" % name for name in names))
            label.ensurePolished()
        finally:
            qInstallMessageHandler(previous)
        return sorted({message[len("Unknown property ") :] for message in seen if message.startswith("Unknown property ")})

    assert unknown(sorted(KNOWN_PROPERTIES)) == []
    assert unknown(["colr", "bakground", "text-shadow", "z-index", "cursor", "display"]) == [
        "bakground",
        "colr",
        "cursor",
        "display",
        "text-shadow",
        "z-index",
    ]


def test_qt_reports_unknown_properties_only_for_rules_that_reach_the_probe() -> None:
    verdict = ask_qt("* { colr: red; }")
    assert verdict is not None and verdict.readable and verdict.unknown_properties == ("colr",)


_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QFrame" name="panel">
     <layout class="QVBoxLayout" name="panelLayout">
      <item><widget class="QPushButton" name="okButton"><property name="flat"><bool>true</bool></property></widget></item>
      <item><widget class="QPushButton" name="cancelButton"/></item>
      <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item><widget class="QPushButton" name="saveButton"/></item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QToolButton" name="moreButton"/></item>
  </layout>
 </widget>
</ui>
"""

_SELECTORS = [
    "QPushButton",
    "QAbstractButton",
    "QWidget",
    "QFrame",
    "QLabel",
    ".QPushButton",
    ".QAbstractButton",
    "#okButton",
    "QPushButton#okButton",
    "QLabel#okButton",
    "QFrame QPushButton",
    "QFrame > QPushButton",
    "Form > QPushButton",
    "Form QPushButton",
    "QFrame > QFrame",
    'QPushButton[flat="true"]',
    "#okButton, #saveButton",
    "QLineEdit, QToolButton",
    "QFrame QLabel, #saveButton",
]


def _red(widget) -> bool:  # type: ignore[no-untyped-def]
    image = widget.grab().toImage()
    color = image.pixelColor(2, 2)
    return (color.red(), color.green(), color.blue()) == (255, 0, 0)


@pytest.mark.parametrize("selector", _SELECTORS)
def test_the_matcher_reaches_the_widgets_qt_styles(selector: str) -> None:
    sheet_text = "%s { background-color: #ff0000; border: none; }" % selector
    with opened(_FORM) as (session, realizer):
        root = realizer.root_widget
        root.resize(360, 360)
        root.setStyleSheet(sheet_text)
        QApplication.processEvents()
        document = session.document
        index = StyleIndex(document)
        found = match_sheet(index, document.root.id, parse_sheet(sheet_text))
        expected = {node_id for node_id in found[0].ids}
        painted = set()
        for node in document.iter_widgets():
            widget = realizer.widget_for(node.id)
            widget.ensurePolished()
            if _red(widget):
                painted.add(node.id)
        names = lambda ids: sorted(document.node(node_id).object_name for node_id in ids)  # noqa: E731
        assert names(painted) == names(expected), selector


def test_a_widgets_own_sheet_reaches_only_its_subtree_like_qt() -> None:
    sheet_text = "QPushButton { background-color: #ff0000; border: none; }"
    with opened(_FORM) as (session, realizer):
        document = session.document
        panel = document.by_name("panel")[0]
        realizer.widget_for(panel).setStyleSheet(sheet_text)
        realizer.root_widget.resize(360, 360)
        QApplication.processEvents()
        index = StyleIndex(document)
        found = match_sheet(index, panel, parse_sheet(sheet_text))
        painted = [
            node.object_name
            for node in document.iter_widgets()
            if _red(realizer.widget_for(node.id))
        ]
        assert sorted(painted) == sorted(document.node(i).object_name for i in found[0].ids) == ["cancelButton", "okButton"]
