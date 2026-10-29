"""Window-file reading and line-boundary stubs (UX-CODE-004, 005, 006, 010)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.window_template import plan_stub, plan_unstub
from app.features.form_builder.engine.project.window_file import read_window
from app.features.form_builder.integration.code_bridge import bridge_edit

_CLASS = '''\
class InvoiceWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)
'''


def _window(body: str, header: str = "") -> str:
    return (
        header
        + "from PySide6.QtWidgets import QDialog\n"
        + "from forms.ui_invoice import Ui_Invoice\n\n"
        + body
    )


def _apply(source: str, start: int, end: int, text: str) -> str:
    return source[:start] + text + source[end:]


def test_the_generated_shape_is_the_window_class() -> None:
    source = _window(_CLASS)
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    assert read.status == "ok"
    assert read.facts.class_name == "InvoiceWindow"
    assert read.facts.methods[0].name == "__init__"


def test_a_class_without_setup_ui_is_not_the_window() -> None:
    source = "class InvoiceWindow(QDialog):\n    pass\n"
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    assert read.status == "ok"
    assert read.facts.class_name == ""


@pytest.mark.parametrize(
    "source",
    [
        _window(_CLASS).replace("\n", "\r\n"),
        _window(_CLASS.replace("    ", "\t")),
        _window(_CLASS, header="# café\n"),
        _window(
            "class InvoiceWindow(QDialog):\n"
            "    def __init__(self, parent=None):\n"
            "        self.ui = Ui_Invoice()\n"
            "        self.ui.setupUi(self)\n"
            "    # keep this comment\n"
        ),
        _window(
            "class InvoiceWindow(QDialog):\n"
            "    def __init__(self, parent=None):\n"
            "        self.ui = Ui_Invoice()\n"
            "        self.ui.setupUi(self)\n"
            "    @property\n"
            "    def title(self):\n"
            "        return ''\n"
        ),
        _window(
            "class InvoiceWindow(QDialog):\n"
            "    def __init__(self, parent=None):\n"
            "        self.ui = Ui_Invoice()\n"
            "        self.ui.setupUi(self)\n"
            "    class Inner:\n"
            "        pass\n"
        ),
        _window(_CLASS + "\nclass Other:\n    pass\n"),
        _window(_CLASS).rstrip("\n"),
        _window(_CLASS, header="# -*- coding: utf-8 -*-\n"),
        _window("class InvoiceWindow(QDialog):\n    pass\n"),
        _window('class InvoiceWindow(QDialog):\n    """The invoice window."""\n'),
    ],
)
def test_a_stub_is_inserted_on_a_line_boundary_and_undo_restores_the_bytes(source: str) -> None:
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    plan = plan_stub(
        read,
        method_name="print_receipt",
        params=(),
        sender="printButton",
        event_words="clicked",
    )
    assert plan.edit.start == plan.edit.end
    updated = _apply(source, plan.edit.start, plan.edit.end, plan.edit.text)
    assert updated.replace(plan.edit.text, "", 1) == source
    prefix = source[: plan.edit.start]
    assert prefix == "" or prefix.endswith(("\n", "\r")) or plan.opened_line
    ast.parse(updated)
    assert "def print_receipt(self):" in updated
    assert '"""Runs when printButton is clicked."""' in updated
    again = read_window("/proj", "forms/invoice_window.py", text=updated)
    back = plan_unstub(
        again, "print_receipt", plan.stub_hash, plan.blank_lines, plan.opened_line
    )
    assert back is not None
    restored = _apply(updated, back.start, back.end, back.text)
    assert restored == source


def test_a_long_arithmetic_line_is_refused_before_parse() -> None:
    source = _window(_CLASS) + "x = " + "+".join(["1"] * 2500) + "\n"
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    assert read.status == "refused"
    assert read.reason == "a line has too many tokens"


def test_brackets_nested_past_the_limit_are_refused() -> None:
    source = _window(_CLASS) + "x = " + ("(" * 120) + "1" + (")" * 120) + "\n"
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    assert read.status == "refused"
    assert "brackets" in read.reason


def test_a_syntax_error_names_the_line_and_does_not_insert(source: str = "") -> None:
    del source
    text = _window(_CLASS) + "def broken(\n"
    read = read_window("/proj", "forms/invoice_window.py", text=text)
    assert read.status == "syntax_error"
    assert read.line > 0
    with pytest.raises(ValueError) as raised:
        plan_stub(read, method_name="save_invoice", params=(), sender="saveButton", event_words="clicked")
    assert "line" in str(raised.value)
    assert "save_invoice" in str(raised.value)


def test_reading_a_base_does_not_import_it(tmp_path: Path) -> None:
    touched = tmp_path / "touched"
    (tmp_path / "shop.py").write_text(
        "open(%r, 'w').write('imported')\nclass ShopWindow:\n    def ready(self):\n        return 1\n" % str(touched),
        encoding="utf-8",
    )
    window = tmp_path / "forms"
    window.mkdir()
    body = (
        "from shop import ShopWindow\n"
        "from forms.ui_invoice import Ui_Invoice\n\n"
        "class InvoiceWindow(ShopWindow):\n"
        "    def __init__(self, parent=None):\n"
        "        self.ui = Ui_Invoice()\n"
        "        self.ui.setupUi(self)\n"
    )
    (window / "invoice_window.py").write_text(body, encoding="utf-8")
    read = read_window(str(tmp_path), "forms/invoice_window.py")
    assert read.status == "ok"
    assert read.facts is not None
    assert any(method.name == "ready" for method in read.facts.base_methods)
    assert not touched.exists()
    assert "shop" not in sys.modules


def test_a_missing_file_is_missing(tmp_path: Path) -> None:
    read = read_window(str(tmp_path), "forms/invoice_window.py")
    assert read.status == "missing"


def test_a_file_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "forms"
    path.mkdir()
    (path / "invoice_window.py").write_bytes(b"# coding: latin-1\n" + "café".encode("latin-1") + b"\n")
    read = read_window(str(tmp_path), "forms/invoice_window.py")
    assert read.status == "refused"
    assert read.reason == "it isn't UTF-8 text"


def test_an_edited_stub_is_left_in_place() -> None:
    source = _window(_CLASS)
    read = read_window("/proj", "forms/invoice_window.py", text=source)
    plan = plan_stub(
        read, method_name="print_receipt", params=(), sender="printButton", event_words="clicked"
    )
    updated = _apply(source, plan.edit.start, plan.edit.end, plan.edit.text)
    updated = updated.replace("pass", "return 1", 1)
    again = read_window("/proj", "forms/invoice_window.py", text=updated)
    assert plan_unstub(again, "print_receipt", plan.stub_hash, plan.blank_lines, plan.opened_line) is None


def test_a_crlf_file_and_its_lf_tab_each_get_whole_line_edits(tmp_path: Path) -> None:
    crlf = _window(_CLASS).replace("\n", "\r\n")
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "invoice_window.py").write_bytes(crlf.encode("utf-8"))
    on_disk = read_window(str(tmp_path), "forms/invoice_window.py")
    disk_plan = plan_stub(
        on_disk, method_name="print_receipt", params=(), sender="printButton", event_words="clicked"
    )
    disk_edit = bridge_edit(disk_plan.edit)
    assert "\r\n" in disk_edit.text
    assert "\n" not in disk_edit.text.replace("\r\n", "")
    disk_updated = _apply(crlf, disk_edit.start, disk_edit.end, disk_edit.text)
    assert disk_updated.endswith("\r\n")
    assert "def print_receipt(self):\r\n" in disk_updated
    tab = crlf.replace("\r\n", "\n")
    in_tab = read_window(str(tmp_path), "forms/invoice_window.py", text=tab)
    tab_plan = plan_stub(
        in_tab, method_name="print_receipt", params=(), sender="printButton", event_words="clicked"
    )
    tab_edit = bridge_edit(tab_plan.edit)
    assert "\r" not in tab_edit.text
    tab_updated = _apply(tab, tab_edit.start, tab_edit.end, tab_edit.text)
    ast.parse(tab_updated)
    assert tab_updated.replace(tab_edit.text, "", 1) == tab
