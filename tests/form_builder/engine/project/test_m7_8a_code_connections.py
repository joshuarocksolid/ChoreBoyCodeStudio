# pyright: reportAttributeAccessIssue=false
"""The window file is parsed, never executed."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.logic.uses import Use
from app.features.form_builder.engine.project.code_connections import read_connections

pytestmark = pytest.mark.unit

_SOURCE = (
    "class InvoiceWindow(object):\n"
    "    def __init__(self):\n"
    "        self.ui.setupUi(self)\n"
    "        self.ui.saveButton.clicked.connect(self.print_invoice)\n"
    "        self.ui.discountEdit.setEnabled(True)\n"
)


def test_connect_and_set_enabled_are_parsed() -> None:
    assert read_connections(_SOURCE, "invoice_window.py") == (
        Use("print_invoice", "call", "code", "saveButton", "", "", -1, "clicked", 4, "invoice_window.py", "print_invoice"),
        Use("saveButton", "call", "code", "saveButton", "", "", -1, "clicked", 4, "invoice_window.py", "print_invoice"),
        Use("discountEdit", "set", "code", "discountEdit", "setEnabled", "cbcsEnabledWhen", -1, "", 5, "invoice_window.py", ""),
    )


def test_a_syntax_error_returns_nothing() -> None:
    assert read_connections("class InvoiceWindow(object):\n    def broken(:\n", "invoice_window.py") == ()


def test_a_class_without_setup_ui_returns_nothing() -> None:
    assert read_connections("class Other(object):\n    def run(self):\n        return None\n", "other.py") == ()
