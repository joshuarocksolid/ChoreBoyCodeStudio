# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Style sheet engine: places in problems, selector matches, and the text edits behind Text colour."""

from __future__ import annotations

from typing import List

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.style.check import LOOKS_RIGHT, check_sheet
from app.features.form_builder.engine.style.colors import parse_color
from app.features.form_builder.engine.style.edit import (
    StyleEditRefused,
    read_color,
    remove_color,
    rename_selector,
    set_color,
)
from app.features.form_builder.engine.style.selectors import StyleIndex, match_sheet, parse_selectors
from app.features.form_builder.engine.style.sheet import parse_sheet
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = [pytest.mark.unit]

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
      <item><widget class="QLabel" name="nameLabel"/></item>
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


def _names(index: StyleIndex, ids) -> List[str]:  # type: ignore[no-untyped-def]
    return [index.facts[node_id].name for node_id in ids]


def _matches(sheet_text: str, owner_name: str = "Form"):  # type: ignore[no-untyped-def]
    document = read_ui(_FORM, allocator=IdAllocator()).document
    index = StyleIndex(document)
    owner = document.by_name(owner_name)[0]
    return index, match_sheet(index, owner, parse_sheet(sheet_text))


def test_a_missing_brace_and_a_missing_semicolon_say_which_line() -> None:
    assert check_sheet("QPushButton {\n    color: red;\n").message == "Line 1: a } is missing."
    assert check_sheet("QLabel { color: red; }\nQPushButton {\n  color: red\n  background: blue;\n}\n").message == (
        "Line 3: a ; is missing after the value."
    )
    assert check_sheet("QLabel {\n  colr: red;\n}").message == "Line 2: “colr” isn't a property Qt knows."
    assert check_sheet("QLabel,\nQPushButton:hovr { color: red; }").message == "Line 2: “hovr” isn't a state Qt knows."
    assert check_sheet("QLabel { color: red; }").message == LOOKS_RIGHT
    assert check_sheet("").message == LOOKS_RIGHT


def test_a_warning_still_applies_and_an_error_does_not() -> None:
    assert check_sheet("QLabel { colr: red; }").applies
    assert not check_sheet("QLabel { color: red;").applies
    # Qt's verdict is final in both directions.
    assert not check_sheet("QLabel { color: red; }", qt_readable=False).applies
    assert check_sheet("QLabel { color: red; }", qt_readable=False).message == "Qt can't read this style sheet."
    assert check_sheet("QLabel { color: red;", qt_readable=True).applies


def test_every_property_name_in_the_sheet_is_checked_case_blind() -> None:
    assert parse_sheet("QLabel { Color: red; qproperty-flat: true; -qt-background-role: base; }").problems == ()


def test_selectors_read_types_ids_attributes_combinators_and_states() -> None:
    first, second = parse_selectors("QFrame > QPushButton#okButton:hover, QLabel[text=\"a\"]")
    assert first.combinators == (">",)
    assert first.parts[1].type_name == "QPushButton" and first.parts[1].ident == "okButton"
    assert first.state_words() == ("hovered",)
    assert second.parts[0].attrs[0].name == "text" and second.parts[0].attrs[0].value == "a"
    assert not parse_selectors("QLabel + QPushButton")[0].valid
    assert not parse_selectors("")[0].valid


def test_a_type_selector_reaches_subclasses_and_a_dot_class_only_the_exact_class() -> None:
    index, found = _matches(
        "QAbstractButton { a: b; } .QPushButton { a: b; } QPushButton { a: b; } #okButton { a: b; } * { a: b; }"
    )
    by_selector = {match.selector: _names(index, match.ids) for match in found}
    assert by_selector["QAbstractButton"] == ["okButton", "cancelButton", "saveButton", "moreButton"]
    assert by_selector[".QPushButton"] == ["okButton", "cancelButton", "saveButton"]
    assert by_selector["QPushButton"] == ["okButton", "cancelButton", "saveButton"]
    assert by_selector["#okButton"] == ["okButton"]
    assert len(by_selector["*"]) == 8


def test_descendant_child_and_attribute_selectors() -> None:
    index, found = _matches(
        "QFrame QPushButton { a: b; } Form > QPushButton { a: b; } QFrame > QLabel { a: b; } QPushButton[flat=\"true\"] { a: b; }"
    )
    names = [_names(index, match.ids) for match in found]
    assert names[0] == ["okButton", "cancelButton"]
    assert names[1] == []
    assert names[2] == ["nameLabel"]
    assert names[3] == ["okButton"]


def test_a_rule_in_a_widgets_own_sheet_reaches_only_its_subtree_and_bare_declarations_wrap_in_star() -> None:
    index, found = _matches("QPushButton { color: red; }", owner_name="panel")
    assert _names(index, found[0].ids) == ["okButton", "cancelButton"]
    index, found = _matches("color: red;", owner_name="panel")
    assert found[0].rule == -1 and _names(index, found[0].ids) == ["panel", "okButton", "cancelButton", "nameLabel"]
    assert parse_sheet("color: red;").rule_count == 1 and parse_sheet("").rule_count == 0


def test_a_rule_that_matches_nothing_has_zero_ids() -> None:
    _index, found = _matches("QProgressBar { color: red; }")
    assert found[0].count == 0


def test_text_colour_goes_into_a_bare_sheet_or_into_a_rule_named_for_the_widget() -> None:
    assert set_color("", (26, 127, 55), "okButton") == "color: #1A7F37;"
    assert set_color("background: red;", (1, 2, 3), "okButton") == "background: red;\ncolor: #010203;"
    assert set_color("color: red; background: blue", (255, 255, 255), "okButton") == "color: #FFFFFF; background: blue"
    ruled = "QPushButton {\n    background: red;\n}\n"
    out = set_color(ruled, (26, 127, 55), "okButton")
    assert out == ruled.rstrip() + "\n\n#okButton {\n    color: #1A7F37;\n}\n"
    assert read_color(out, "okButton") == "#1A7F37"
    again = set_color(out, (0, 0, 0), "okButton")
    assert read_color(again, "okButton") == "#000000" and again.count("#okButton") == 1
    # The rule is kept when the colour is added to a rule that already exists, without a final semicolon.
    assert set_color("#okButton { background: red }", (1, 2, 3), "okButton") == (
        "#okButton { background: red;\n    color: #010203;\n}"
    )
    with pytest.raises(StyleEditRefused):
        set_color("QPushButton { color: red;", (1, 2, 3), "okButton")


def test_reset_removes_only_the_colour_and_the_rule_or_sheet_it_leaves_empty() -> None:
    assert remove_color("color: #1A7F37;", "okButton") == ""
    assert remove_color("color: #1A7F37;\nbackground: red;", "okButton") == "background: red;"
    text = "QLabel { color: blue; }\n\n#okButton {\n    color: #1A7F37;\n}\n"
    assert remove_color(text, "okButton") == "QLabel { color: blue; }\n\n"
    assert remove_color("#okButton {\n    color: #1A7F37;\n    margin: 1px;\n}", "okButton") == "#okButton {\n    margin: 1px;\n}"
    assert remove_color("QLabel { color: blue; }", "okButton") == "QLabel { color: blue; }"


def test_a_rename_rewrites_the_selector_and_never_a_hex_colour() -> None:
    text = "#okButton { color: #fff; }\nQFrame #okButton, #okButtonX { margin: 0; }\n"
    assert rename_selector(text, "okButton", "acceptButton") == (
        "#acceptButton { color: #fff; }\nQFrame #acceptButton, #okButtonX { margin: 0; }\n"
    )
    assert rename_selector("color: #fff;", "fff", "x") == "color: #fff;"


def test_colours_read_back() -> None:
    assert parse_color("#1a7f37") == (26, 127, 55)
    assert parse_color("#fff") == (255, 255, 255)
    assert parse_color("rgb(1, 2, 3)") == (1, 2, 3)
    assert parse_color("red") == (255, 0, 0)
    assert parse_color("notacolour") is None


_SHEETS = _FORM.replace(
    '<widget class="QWidget" name="Form">',
    '<widget class="QWidget" name="Form"><property name="styleSheet"><string>#okButton { margin: 1px; }\n'
    "QLabel { color: #fff; }</string></property>",
).replace(
    '<widget class="QPushButton" name="okButton">',
    '<widget class="QPushButton" name="okButton"><property name="styleSheet"><string>#okButton { color: #1A7F37; }</string></property>',
)


def test_a_rename_rewrites_every_selector_that_names_the_widget_in_the_same_undo_step() -> None:
    from app.features.form_builder.engine.commands.catalog import Rename
    from tests.form_builder.engine.commands._support import nid, open_log, saved

    log = open_log(_SHEETS)
    document = log.document
    before = saved(document)
    log.execute(Rename(nid(document, "okButton"), "acceptButton"))
    root_sheet = document.root.value("styleSheet").text
    own_sheet = document.node(nid(document, "acceptButton")).value("styleSheet").text
    assert root_sheet == "#acceptButton { margin: 1px; }\nQLabel { color: #fff; }"
    assert own_sheet == "#acceptButton { color: #1A7F37; }"
    assert log.undo()
    assert document.root.value("styleSheet").text.startswith("#okButton")
    assert saved(document) == before


def test_one_sheet_text_is_read_once_however_many_rows_and_checks_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    """An apply asks for the same sheet from the colour rows, the override check and the drawer: one read (the 100 ms budget)."""
    from app.features.form_builder.engine.style import sheet as sheet_module

    reads: List[str] = []
    real = sheet_module.tokenize

    def counting(text: str):  # noqa: ANN202
        reads.append(text)
        return real(text)

    monkeypatch.setattr(sheet_module, "tokenize", counting)
    sheet_module.parse_sheet.cache_clear()
    text = "QPushButton { color: #1A7F37; }\n#okButton { background: #fff; }"
    for _ in range(5):
        read_color(text, "okButton")
    assert reads == [text]
