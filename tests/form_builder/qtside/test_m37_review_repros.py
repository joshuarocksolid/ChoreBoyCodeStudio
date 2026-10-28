# pyright: reportAttributeAccessIssue=false
"""M3.7 review repros: real main window, keys only."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session, _walk_to  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_ROWS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>C</class>
 <widget class="QWidget" name="C">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>300</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property><property name="buddy"><cstring>nameEdit</cstring></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
   <item row="1" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property><property name="buddy"><cstring>emailEdit</cstring></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
   <item row="2" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property><property name="buddy"><cstring>phoneEdit</cstring></property></widget></item>
   <item row="2" column="1"><widget class="QLineEdit" name="phoneEdit"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_wrapping_fields_of_two_form_rows_writes_clean_box_items(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "emailEdit")
        kb.press("Key_Down", "Shift")
        assert set(kb.selected()) == {"emailEdit", "phoneEdit"}
        kb.press("Key_1", "Control")
        text = kb.text()
        box = text[text.index('<layout class="QHBoxLayout"') : text.index("</layout>", text.index("QHBoxLayout"))]
        assert re.search(r'<item row="\d+"', box) is None, "box layout items carry grid cells:\n" + box
        # The Phone label must not be left as a row without a field.
        rows = re.findall(r'<item row="(\d+)" column="(\d+)">\s*<widget class="QLabel" name="phoneLabel"', text)
        assert not rows, "phoneLabel is left on a row of its own: %s" % rows
    finally:
        _close(window, qapp, guard)


def test_alt_up_moves_a_row_just_inserted(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS)
    try:
        kb.press("Key_1", "Alt")
        _walk_to(kb, "phoneEdit", key="Key_Down")
        kb.press("Key_Slash")
        insert_list = kb.focus()
        for _ in range(12):
            item = insert_list.currentItem()  # type: ignore[union-attr]
            if item is not None and item.text() == "Line edit":
                break
            kb.press("Key_Down")
        kb.press("Key_Return")
        kb.type("Fax")
        kb.press("Key_Return")
        added = [name for name in kb.selected() if name != "label"]
        kb.log.append("selection after insert: %s (current %s)" % (kb.selected(), kb.current()))
        before = kb.text()
        kb.press("Key_3", "Alt")
        kb.press("Key_Up", "Alt")
        after = kb.text()
        assert after != before, "Alt+Up after inserting a row moved nothing\n" + kb.history()
        assert after.index('name="%s"' % added[0]) < after.index('name="phoneEdit"'), kb.history()
    finally:
        _close(window, qapp, guard)


def test_the_status_bar_names_a_selected_layout(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "emailEdit")
        kb.press("Key_Down", "Shift")
        kb.press("Key_1", "Control")
        assert kb.current() == "horizontalLayout"
        sentence = str(kb.surface.editor_status_sentence())  # type: ignore[attr-defined]
        assert sentence.startswith("horizontalLayout"), sentence
    finally:
        _close(window, qapp, guard)


# M3.7d1 re-review. The rows are written out of order on purpose: Phone is
# row 1 on screen but last in the file, the way an insert writes it.
_ROWS_OUT_OF_ORDER = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>C</class>
 <widget class="QWidget" name="C">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>300</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property><property name="buddy"><cstring>nameEdit</cstring></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
   <item row="2" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property><property name="buddy"><cstring>emailEdit</cstring></property></widget></item>
   <item row="2" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
   <item row="1" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property><property name="buddy"><cstring>phoneEdit</cstring></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="phoneEdit"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _box_names(text: str) -> list:
    start = text.index('<layout class="QHBoxLayout"')
    box = text[start : text.index("</layout>", start)]
    return re.findall(r'<widget class="\w+" name="(\w+)"', box)


def test_a_wrap_of_form_rows_keeps_the_rows_reading_order(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS_OUT_OF_ORDER)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "phoneEdit")
        kb.press("Key_Down", "Shift")
        assert set(kb.selected()) == {"phoneEdit", "emailEdit"}, kb.history()
        kb.press("Key_1", "Control")
        text = kb.text()
        names = _box_names(text)
        assert names.index("phoneEdit") < names.index("emailEdit"), names
        form_rows = [int(row) for row in re.findall(r'<item row="(\d+)"', text)]
        assert form_rows, text
        assert sorted(set(form_rows)) == list(range(max(form_rows) + 1)), form_rows
    finally:
        _close(window, qapp, guard)


def test_a_wrap_of_form_rows_keeps_the_first_label_in_the_label_column(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "emailEdit")
        kb.press("Key_Down", "Shift")
        kb.press("Key_1", "Control")
        text = kb.text()
        assert re.search(r'<item row="(\d+)" column="0">\s*<widget class="QLabel" name="emailLabel"', text), text
        assert re.search(r'<item row="\d+" column="1">\s*<layout class="QHBoxLayout"', text), text
        assert _box_names(text) == ["emailEdit", "phoneLabel", "phoneEdit"], _box_names(text)
    finally:
        _close(window, qapp, guard)


def test_a_button_inserted_into_a_form_has_no_field_label(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _ROWS)
    try:
        kb.press("Key_1", "Alt")
        _walk_to(kb, "phoneEdit", key="Key_Down")
        kb.press("Key_Slash")
        insert_list = kb.focus()
        for _ in range(12):
            item = insert_list.currentItem()  # type: ignore[union-attr]
            if item is not None and item.text() == "Button":
                break
            kb.press("Key_Down")
        kb.press("Key_Return")
        if kb.focus_name() != "formBuilder.structure" and not kb.focus_in("formBuilder.canvas"):
            kb.press("Key_Escape")
        assert "New field:" not in kb.text(), kb.history()
    finally:
        _close(window, qapp, guard)


def test_f8_says_where_the_tab_order_comes_from(tmp_path: Path, qapp: QApplication) -> None:
    """Until the M5.6 overlay, F8 explains the order, and must be true for this file."""
    custom = _ROWS.replace(" <resources/>", " <tabstops>\n  <tabstop>phoneEdit</tabstop>\n  <tabstop>nameEdit</tabstop>\n </tabstops>\n <resources/>")
    for text, expected in ((_ROWS, "follows the order of widgets"), (custom, "keeps its own tab order")):
        window, kb, guard = _session(tmp_path / expected.split()[0], qapp, text)
        try:
            kb.press("Key_3", "Alt")
            kb.press("Key_F8")
            sentence = str(kb.surface.editor_status_sentence())  # type: ignore[attr-defined]
            assert expected in sentence, sentence
            assert kb.focus_in("formBuilder.canvas")
        finally:
            _close(window, qapp, guard)
