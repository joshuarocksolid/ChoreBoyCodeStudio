# pyright: reportAttributeAccessIssue=false
"""The logic table for the invoice form: rules, one check, one step, and the window file."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.checks import Required, write_checks
from app.features.form_builder.engine.logic.events_codec import call_step, write_list
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.uses import Use, collect, of_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_INVOICE = Path(__file__).resolve().parents[2] / "fixtures" / "m7" / "forms" / "invoice.ui"
_RELATIVE = "invoice_window.py"

_DISCOUNT_READ = Use(
    "discountCheck", "read", "rule", "discountEdit", "discountCheck", "cbcsEnabledWhen", -1, "", 0, "", ""
)
_DISCOUNT_SET = Use(
    "discountEdit", "set", "rule", "discountEdit", "discountCheck", "cbcsEnabledWhen", -1, "", 0, "", ""
)
_DISCOUNT_CODE = Use(
    "discountEdit", "set", "code", "discountEdit", "setEnabled", "cbcsEnabledWhen", -1, "", 5, _RELATIVE, ""
)
_TOTAL_SET = Use(
    "lineTotalLabel", "set", "rule", "lineTotalLabel", "qtySpin * priceSpin", "cbcsValue", -1, "", 0, "", ""
)
_QTY_READ = Use(
    "qtySpin", "read", "rule", "lineTotalLabel", "qtySpin * priceSpin", "cbcsValue", -1, "", 0, "", ""
)
_PRICE_READ = Use(
    "priceSpin", "read", "rule", "lineTotalLabel", "qtySpin * priceSpin", "cbcsValue", -1, "", 0, "", ""
)
_EMAIL = Use("emailEdit", "read", "check", "emailEdit", "required", "cbcsValidate", 0, "", 0, "", "")
_SAVE_STEP = Use(
    "saveButton", "call", "step", "saveButton", "save_invoice", "cbcsOnClicked", 0, "clicked", 0, "", ""
)
_SAVE_METHOD = Use(
    "save_invoice", "call", "step", "saveButton", "", "cbcsOnClicked", 0, "clicked", 0, "", "save_invoice"
)
_PRINT = Use(
    "print_invoice", "call", "code", "saveButton", "", "", -1, "clicked", 4, _RELATIVE, "print_invoice"
)
_SAVE_CODE = Use(
    "saveButton", "call", "code", "saveButton", "", "", -1, "clicked", 4, _RELATIVE, "print_invoice"
)
_BOOK = (
    _DISCOUNT_SET,
    _DISCOUNT_READ,
    _TOTAL_SET,
    _QTY_READ,
    _PRICE_READ,
    _EMAIL,
    _SAVE_STEP,
    _SAVE_METHOD,
    _PRINT,
    _SAVE_CODE,
    _DISCOUNT_CODE,
)


def window_source() -> str:
    return (
        "class InvoiceWindow(object):\n"
        "    def __init__(self):\n"
        "        self.ui.setupUi(self)\n"
        "        self.ui.saveButton.clicked.connect(self.print_invoice)\n"
        "        self.ui.discountEdit.setEnabled(True)\n"
        "\n"
        "    def save_invoice(self):\n"
        "        return None\n"
        "\n"
        "    def print_invoice(self):\n"
        "        return None\n"
    )


def _prop(name: str, text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return '<property name="%s" stdset="0"><string notr="true">%s</string></property>' % (name, escaped)


def invoice_text() -> str:
    checks = write_checks((Required("Enter an email address"),))
    assert checks is not None
    steps = write_list((call_step("save_invoice"),))
    text = _INVOICE.read_text(encoding="utf-8")
    text = text.replace(
        '<widget class="QLineEdit" name="discountEdit"/>',
        '<widget class="QLineEdit" name="discountEdit">%s</widget>' % _prop("cbcsEnabledWhen", "discountCheck"),
    )
    text = text.replace(
        '<item row="0" column="0">',
        (
            '<item row="4" column="0">'
            '<widget class="QLabel" name="discountRateLabel">'
            '<property name="text"><string>Discount rate</string></property>'
            '<property name="buddy"><cstring>discountEdit</cstring></property>'
            "</widget></item>"
            '<item row="0" column="0">'
        ),
        1,
    )
    text = text.replace(
        '<widget class="QLabel" name="lineTotalLabel"/>',
        '<widget class="QLabel" name="lineTotalLabel">%s</widget>' % _prop("cbcsValue", "qtySpin * priceSpin"),
    )
    text = text.replace(
        '<widget class="QLineEdit" name="emailEdit"/>',
        '<widget class="QLineEdit" name="emailEdit">%s</widget>' % _prop("cbcsValidate", checks),
    )
    text = text.replace(
        "</widget>\n   </item>\n  </layout>\n </widget>",
        "%s</widget>\n   </item>\n  </layout>\n </widget>" % _prop("cbcsOnClicked", steps),
    )
    return text


def test_invoice_uses_and_the_one_fight() -> None:
    doc = read_ui(invoice_text(), allocator=IdAllocator()).document
    env = env_for(doc, None, QtClassTable.shared())
    book = collect(doc, env, window_source(), _RELATIVE)
    assert book.uses == _BOOK
    assert of_name(book, "discountCheck") == (_DISCOUNT_READ,)
    assert of_name(book, "discountEdit") == (_DISCOUNT_SET, _DISCOUNT_CODE)
    assert of_name(book, "qtySpin") == (_QTY_READ,)
    assert of_name(book, "priceSpin") == (_PRICE_READ,)
    assert of_name(book, "lineTotalLabel") == (_TOTAL_SET,)
    assert of_name(book, "emailEdit") == (_EMAIL,)
    assert of_name(book, "saveButton") == (_SAVE_STEP, _SAVE_CODE)
    assert of_name(book, "save_invoice") == (_SAVE_METHOD,)
    assert of_name(book, "print_invoice") == (_PRINT,)
    assert len(book.diagnostics) == 1
    found = book.diagnostics[0]
    assert found.code == "FB207"
    assert found.severity == CODES["FB207"].severity
    assert found.fixes == ()
    assert found.source == "logic.code"
    assert found.message == (
        "Your code calls self.ui.discountEdit.setEnabled(...), but an Enabled when rule also controls it. "
        "The rule wins on every refresh."
    )
    assert found.location.object_name == "discountEdit"
    assert found.location.property == "cbcsEnabledWhen"
    assert found.location.code_path == _RELATIVE
    assert found.location.code_line == 5
    assert found.location.node_id == doc.by_name("discountEdit")[0]
