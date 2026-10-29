"""FB201–FB213, each with the row that should appear and the clean twin."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.handler_checks import check_handlers
from app.features.form_builder.engine.project.window_file import read_window
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <widget class="QPushButton" name="okButton">
   <property name="text"><string>OK</string></property>
   %(extra)s
  </widget>
 </widget>
 %(tail)s
</ui>
"""

_HEAD = (
    "from PySide6.QtWidgets import QDialog\n"
    "from forms.ui_invoice import Ui_Invoice\n\n"
    "class InvoiceWindow(QDialog):\n"
    "    def __init__(self, parent=None):\n"
    "        super().__init__(parent)\n"
    "        self.ui = Ui_Invoice()\n"
    "        self.ui.setupUi(self)\n"
)

_INHERITED = frozenset({"close", "accept", "reject", "show", "hide"})


def _doc(tail: str = "", extra: str = ""):
    text = _UI % {"tail": tail, "extra": extra}
    return read_ui(text, allocator=IdAllocator()).document


def _codes(window: str, doc=None, **kwargs):
    if doc is None:
        doc = _doc(
            tail=(
                "<connections><connection>"
                "<sender>okButton</sender><signal>clicked()</signal>"
                "<receiver>Invoice</receiver><slot>save_invoice()</slot>"
                "</connection></connections>"
            )
        )
    read = read_window("/proj", "forms/invoice_window.py", text=window)
    found = check_handlers(
        doc,
        read,
        classes=QtClassTable.shared(),
        registry=(),
        inherited=kwargs.get("inherited", _INHERITED),
        connect_by_name=kwargs.get("connect_by_name", True),
    )
    return {item.code: item for item in found}


@pytest.mark.logic("L-signature-checks")
def test_fb201_a_missing_method_and_its_clean_twin() -> None:
    missing = _codes(_HEAD)
    assert "FB201" in missing
    assert missing["FB201"].fixes[0].title == "Create method"
    defined = _HEAD + "    def save_invoice(self):\n        return 1\n"
    assert "FB201" not in _codes(defined)


@pytest.mark.logic("L-signature-checks")
def test_fb202_too_many_required_parameters_and_its_clean_twin() -> None:
    wide = _HEAD + "    def save_invoice(self, left, right):\n        return left\n"
    assert "FB202" in _codes(wide)
    optional = _HEAD + "    def save_invoice(self, checked=False):\n        return checked\n"
    assert "FB202" not in _codes(optional)


@pytest.mark.logic("L-signature-checks")
def test_fb203_an_empty_method_is_info_and_a_body_is_clean() -> None:
    empty = _HEAD + "    def save_invoice(self):\n        pass\n"
    found = _codes(empty)
    assert found["FB203"].severity is Severity.INFO
    filled = _HEAD + "    def save_invoice(self):\n        return 1\n"
    assert "FB203" not in _codes(filled)


def test_fb204_a_method_that_replaces_a_qt_method_and_its_clean_twin() -> None:
    shadow = _HEAD + "    def close(self):\n        return 1\n"
    doc = _doc()
    found = _codes(shadow, doc=doc)
    assert "FB204" in found
    assert "QDialog" in found["FB204"].message
    assert "FB204" not in _codes(_HEAD + "    def save_invoice(self):\n        return 1\n")


@pytest.mark.logic("L-connect-slots-by-name")
def test_fb205_a_name_that_also_auto_connects_and_its_clean_twin() -> None:
    window = (
        _HEAD
        + "    @Slot()\n"
        + "    def on_okButton_clicked(self):\n"
        + "        return 1\n"
    )
    doc = _doc(
        tail=(
            "<connections><connection>"
            "<sender>okButton</sender><signal>clicked()</signal>"
            "<receiver>Invoice</receiver><slot>on_okButton_clicked()</slot>"
            "</connection></connections>"
        )
    )
    assert "FB205" in _codes(window, doc=doc)
    plain = _HEAD + "    def save_invoice(self):\n        return 1\n"
    assert "FB205" not in _codes(plain)


@pytest.mark.logic("L-connect-slots-by-name")
def test_fb206_a_by_name_method_without_slot_and_the_decorated_twin() -> None:
    bare = _HEAD + "    def on_okButton_clicked(self):\n        return 1\n"
    assert "FB206" in _codes(bare, doc=_doc())
    decorated = _HEAD + "    @Slot()\n    def on_okButton_clicked(self):\n        return 1\n"
    assert "FB206" not in _codes(decorated, doc=_doc())


@pytest.mark.pain("P-22")
@pytest.mark.logic("L-connect-slots-by-name")
def test_fb208_a_misspelled_signal_is_a_row_and_the_real_name_is_clean() -> None:
    """Pain 22. on_okButton_clickd is a problem. on_okButton_clicked with @Slot is not."""
    miss = _HEAD + "    def on_okButton_clickd(self):\n        return 1\n"
    found = _codes(miss, doc=_doc())
    assert "FB208" in found
    assert "clicked" in found["FB208"].message
    clean = _HEAD + "    @Slot()\n    def on_okButton_clicked(self):\n        return 1\n"
    clean_rows = _codes(clean, doc=_doc())
    assert "FB208" not in clean_rows
    assert "FB206" not in clean_rows


def test_fb209_a_syntax_error_hides_every_other_code() -> None:
    read = read_window("/proj", "forms/invoice_window.py", text=_HEAD + "def broken(\n")
    rows = check_handlers(
        _doc(), read, classes=QtClassTable.shared(), inherited=_INHERITED, connect_by_name=True
    )
    assert [item.code for item in rows] == ["FB209"]


def test_fb210_no_window_class_and_its_clean_twin() -> None:
    read = read_window("/proj", "forms/invoice_window.py", text="x = 1\n")
    rows = check_handlers(_doc(), read, classes=QtClassTable.shared(), inherited=_INHERITED)
    assert [item.code for item in rows] == ["FB210"]
    assert "FB210" not in _codes(_HEAD + "    def save_invoice(self):\n        return 1\n")


@pytest.mark.logic("L-connect-slots-by-name")
def test_fb211_by_name_methods_stay_quiet_when_the_setting_is_on() -> None:
    window = _HEAD + "    @Slot()\n    def on_okButton_clicked(self):\n        return 1\n"
    assert "FB211" in _codes(window, doc=_doc(), connect_by_name=False)
    assert "FB211" not in _codes(window, doc=_doc(), connect_by_name=True)


@pytest.mark.logic("L-signature-checks")
def test_fb212_an_unreadable_base_and_a_base_that_can_be_read(tmp_path: Path) -> None:
    body = (
        "from shop import ShopWindow\n"
        "from forms.ui_invoice import Ui_Invoice\n\n"
        "class InvoiceWindow(ShopWindow):\n"
        "    def __init__(self, parent=None):\n"
        "        self.ui = Ui_Invoice()\n"
        "        self.ui.setupUi(self)\n"
    )
    missing = read_window(str(tmp_path), "forms/invoice_window.py", text=body)
    doc = _doc(
        tail=(
            "<connections><connection>"
            "<sender>okButton</sender><signal>clicked()</signal>"
            "<receiver>Invoice</receiver><slot>ready()</slot>"
            "</connection></connections>"
        )
    )
    rows = check_handlers(doc, missing, classes=QtClassTable.shared(), inherited=_INHERITED)
    assert any(item.code == "FB212" for item in rows)
    assert not any(item.code == "FB201" for item in rows)
    (tmp_path / "shop.py").write_text(
        "class ShopWindow:\n    def ready(self):\n        return 1\n",
        encoding="utf-8",
    )
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "invoice_window.py").write_text(body, encoding="utf-8")
    found = read_window(str(tmp_path), "forms/invoice_window.py")
    clean = check_handlers(doc, found, classes=QtClassTable.shared(), inherited=_INHERITED)
    assert not any(item.code == "FB212" for item in clean)
    assert not any(item.code == "FB201" for item in clean)


@pytest.mark.logic("L-signature-checks")
def test_fb213_a_static_method_and_a_normal_method() -> None:
    static = _HEAD + "    @staticmethod\n    def save_invoice():\n        return 1\n"
    assert "FB213" in _codes(static)
    normal = _HEAD + "    def save_invoice(self):\n        return 1\n"
    assert "FB213" not in _codes(normal)


def test_a_call_step_in_a_property_is_checked_like_a_connection() -> None:
    extra = (
        '<property name="cbcsOnClicked"><string notr="true">'
        '[{"do": "call", "method": "save_invoice"}]'
        "</string></property>"
    )
    doc = _doc(extra=extra)
    assert "FB201" in _codes(_HEAD, doc=doc)


def test_fb207_is_declared_and_not_emitted_for_a_method_call() -> None:
    assert CODES["FB207"].severity is Severity.WARNING
    assert "FB207" not in _codes(_HEAD + "    def save_invoice(self):\n        return 1\n")


@pytest.mark.parametrize(
    "code",
    ["FB%d" % n for n in list(range(201, 207)) + list(range(208, 214))],
)
def test_each_fb2xx_code_is_declared(code: str) -> None:
    assert code in CODES
    assert CODES[code].blocks_visual_open is False
