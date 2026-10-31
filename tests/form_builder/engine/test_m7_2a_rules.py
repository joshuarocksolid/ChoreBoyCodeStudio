# pyright: reportAttributeAccessIssue=false
"""M7.2a rules engine: order, cycles, defaults, scenarios 1 and 2, repair."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.repair import repair_references, widget_classes
from app.features.form_builder.engine.logic.rules import rule_graph
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_FORMS = Path(__file__).resolve().parents[1] / "fixtures" / "m7" / "forms"
_INVOICE = _FORMS / "invoice.ui"
_WINDOW = _FORMS / "invoice_window.py"


def _prop(name: str, text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return '<property name="%s" stdset="0"><string notr="true">%s</string></property>' % (name, escaped)


def _form(body: str, name: str = "Form") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>%s</class>\n'
        ' <widget class="QDialog" name="%s">\n  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "%s\n  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
    ) % (name, name, body)


def _widget(class_name: str, name: str, props: str = "") -> str:
    return '<item><widget class="%s" name="%s">%s</widget></item>' % (class_name, name, props)


def _load(text: str, name: str, tmp_path: Path, trace: bool = False):
    path = tmp_path / ("%s.ui" % name)
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / ("ui_%s.py" % name)),
        window_path=str(tmp_path / ("%s_window.py" % name)),
        module_name="ui_%s" % name,
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"), trace=trace)
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    ast.parse(result.text, filename="ui_%s.py" % name, feature_version=(3, 9))
    return read.document, result


def _scenario1() -> str:
    text = _INVOICE.read_text(encoding="utf-8")
    return text.replace(
        '<widget class="QLineEdit" name="discountEdit"/>',
        '<widget class="QLineEdit" name="discountEdit">%s</widget>' % _prop("cbcsEnabledWhen", "discountCheck"),
    )


def _scenario2() -> str:
    text = _INVOICE.read_text(encoding="utf-8")
    props = _prop("cbcsValue", "qtySpin * priceSpin") + _prop("cbcsFormat", "money")
    return text.replace(
        '<widget class="QLabel" name="lineTotalLabel"/>',
        '<widget class="QLabel" name="lineTotalLabel">%s</widget>' % props,
    )


def test_scenario1_matches_the_listing_and_runs(tmp_path: Path) -> None:
    _doc, result = _load(_scenario1(), "invoice", tmp_path)
    text = result.text or ""
    assert "def cbcs_refresh(self, *args):" in text
    assert "if self._cbcs_refreshing:" in text
    assert "self._cbcs_refreshing = True" in text
    assert "self._cbcs_refreshing = False" in text
    assert "self.discountCheck.toggled.connect(self.cbcs_refresh)" in text
    assert "self.discountEdit.setEnabled(self.discountCheck.isChecked())" in text
    assert "# discountEdit: Enabled when  discountCheck" in text
    assert "Discount" in text
    assert "QCheckBox" in text
    _run_scenario1(text)


def test_scenario2_matches_the_listing_and_runs(tmp_path: Path) -> None:
    _doc, result = _load(_scenario2(), "invoice", tmp_path)
    text = result.text or ""
    assert "self.qtySpin.value()" in text
    assert "_cbcs_dec(self.priceSpin.value(), 2)" in text
    assert "_cbcs_money" in text
    assert "self.lineTotalLabel.setText" in text
    assert "qtySpin.valueChanged.connect(self.cbcs_refresh)" in text
    assert "priceSpin.valueChanged.connect(self.cbcs_refresh)" in text
    assert "lineTotalLabel: Value =  qtySpin * priceSpin" in text
    assert "(format: money)" in text
    _run_scenario2(text)


def test_blank_and_divide_by_zero(tmp_path: Path) -> None:
    body = "\n".join(
        (
            _widget("QLineEdit", "amount", _prop("cbcsKind", "number")),
            _widget("QLineEdit", "units", _prop("cbcsKind", "number")),
            _widget(
                "QLabel",
                "result",
                _prop("cbcsValue", "amount / units") + _prop("cbcsFormat", "money"),
            ),
        )
    )
    _doc, result = _load(_form(body, "Math"), "math", tmp_path)
    text = result.text or ""
    assert 'setToolTip("Can\'t divide by zero")' in text
    _run_divide(text)


def test_chain_refreshes_in_topological_order_and_tree_ties(tmp_path: Path) -> None:
    body = "\n".join(
        (
            _widget("QLineEdit", "a", _prop("cbcsValue", '"x"')),
            _widget("QLineEdit", "b", _prop("cbcsValue", "a")),
            _widget("QLineEdit", "c", _prop("cbcsValue", "b")),
            _widget("QCheckBox", "flagA"),
            _widget("QLineEdit", "editA", _prop("cbcsEnabledWhen", "flagA")),
            _widget("QCheckBox", "flagB"),
            _widget("QLineEdit", "editB", _prop("cbcsEnabledWhen", "flagB")),
        )
    )
    doc, result = _load(_form(body), "chain", tmp_path)
    text = result.text or ""
    value_a = text.index("# a: Value")
    value_b = text.index("# b: Value")
    value_c = text.index("# c: Value")
    assert value_a < value_b < value_c
    enabled_a = text.index("# editA: Enabled when")
    enabled_b = text.index("# editB: Enabled when")
    assert value_c < enabled_a < enabled_b
    env = env_for(doc, None, QtClassTable.shared())
    first = rule_graph(doc, env)
    second = rule_graph(doc, env)
    assert first is second
    assert [item.widget for item in first.order() if item.key == "cbcsValue"] == ["a", "b", "c"]


def test_cycle_generates_nothing_and_every_node_is_fb104(tmp_path: Path) -> None:
    body = "\n".join(
        (
            _widget("QLineEdit", "alpha", _prop("cbcsValue", "beta")),
            _widget("QLineEdit", "beta", _prop("cbcsValue", "alpha")),
        )
    )
    doc, result = _load(_form(body), "cycle", tmp_path)
    text = result.text or ""
    assert "def cbcs_refresh" not in text
    assert "setText" not in text
    codes = [item for item in result.diagnostics if item.code == "FB104"]
    assert {item.location.object_name for item in codes} == {"alpha", "beta"}
    assert codes[0].message.startswith("These values depend on each other in a circle:")
    env = env_for(doc, None, QtClassTable.shared())
    graph = rule_graph(doc, env)
    assert graph.order() == ()
    assert len(graph.cycles()) == 1


def test_defaults_run_once_before_refresh_and_a_calculated_read_is_fb104(tmp_path: Path) -> None:
    body = "\n".join(
        (
            _widget("QLineEdit", "nameEdit", _prop("cbcsDefault", '"Ada"')),
            _widget("QLineEdit", "calc", _prop("cbcsValue", '"x"')),
            _widget("QLineEdit", "bad", _prop("cbcsDefault", "calc")),
        )
    )
    doc, result = _load(_form(body), "defaults", tmp_path)
    text = result.text or ""
    assert "def _cbcs_apply_defaults" in text
    apply_at = text.index("self._cbcs_apply_defaults()")
    refresh_at = text.index("self.cbcs_refresh()")
    assert apply_at < refresh_at
    assert '"Ada"' in text or "'Ada'" in text
    defaults_body = text.split("def _cbcs_apply_defaults", 1)[1].split("def cbcs_refresh", 1)[0]
    assert "nameEdit" in defaults_body
    assert "bad" not in defaults_body
    messages = [item.message for item in result.diagnostics if item.code == "FB104"]
    assert "A default can't read a calculated field" in messages
    env = env_for(doc, None, QtClassTable.shared())
    graph = rule_graph(doc, env)
    assert [item.widget for item in graph.defaults()] == ["nameEdit"]


def test_window_file_and_qt_properties_stay(tmp_path: Path) -> None:
    window = tmp_path / "invoice_window.py"
    original = _WINDOW.read_bytes()
    window.write_bytes(original)
    text = _scenario1()
    path = tmp_path / "invoice.ui"
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_invoice.py"),
        window_path=str(window),
        module_name="ui_invoice",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None
    assert window.read_bytes() == original
    assert "Discount" in result.text
    assert "QLineEdit" in result.text


def test_trace_lines_when_asked(tmp_path: Path) -> None:
    _doc, result = _load(_scenario1(), "invoice", tmp_path, trace=True)
    assert "_cbcs_trace('rule'" in (result.text or "") or '_cbcs_trace("rule"' in (result.text or "")


def test_repair_pairs_a_missing_name_with_a_new_widget_of_the_same_class() -> None:
    body = _widget("QLineEdit", "fresh", _prop("cbcsValue", "oldName"))
    doc = read_ui(_form(body), allocator=IdAllocator()).document
    fixes = repair_references(doc, {"oldName": "QLineEdit", "gone": "QLineEdit"})
    assert len(fixes) == 1
    assert fixes[0].owner == "fresh"
    assert fixes[0].missing == "oldName"
    assert fixes[0].candidates == ("fresh",)
    none = repair_references(doc, {"oldName": "QSpinBox"})
    assert none == ()
    parsed = widget_classes("self.oldName = QtWidgets.QLineEdit(Form)\nself.fresh = QtWidgets.QLineEdit(Form)\n")
    assert parsed == {"oldName": "QLineEdit", "fresh": "QLineEdit"}


def test_env_for_reads_the_invoice_widgets() -> None:
    doc = read_ui(_INVOICE.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    env = env_for(doc, None, QtClassTable.shared())
    check = env.widgets["discountCheck"]
    assert check.class_name == "QCheckBox"
    assert check.display == "Discount"
    assert env.widgets["priceSpin"].decimals == 2
    assert env.widgets["priceSpin"].class_name == "QDoubleSpinBox"
    assert env.widgets["qtyLabel"].display == "Qty"
    again = env_for(doc, None, QtClassTable.shared())
    assert again is env


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _ui(source: str, class_name: str) -> Any:
    namespace: Dict[str, Any] = {}
    exec(compile(source, "ui_form.py", "exec"), namespace)
    return namespace[class_name]


def _run_scenario1(source: str) -> None:
    _app()
    from PySide6.QtWidgets import QDialog

    ui = _ui(source, "Ui_Invoice")()
    host = QDialog()
    ui.setupUi(host)
    assert ui.discountEdit.isEnabled() is False
    ui.discountCheck.setChecked(True)
    assert ui.discountEdit.isEnabled() is True
    ui.discountCheck.setChecked(False)
    assert ui.discountEdit.isEnabled() is False
    host.close()


def _run_scenario2(source: str) -> None:
    _app()
    from PySide6.QtWidgets import QDialog

    ui = _ui(source, "Ui_Invoice")()
    host = QDialog()
    ui.setupUi(host)
    ui.qtySpin.setValue(2)
    ui.priceSpin.setValue(3)
    assert ui.lineTotalLabel.text() == "$6.00"
    host.close()


def _run_divide(source: str) -> None:
    _app()
    from PySide6.QtWidgets import QDialog

    ui = _ui(source, "Ui_Math")()
    host = QDialog()
    ui.setupUi(host)
    ui.amount.setText("10")
    ui.units.setText("")
    assert ui.result.text() == ""
    assert ui.result.toolTip() != "Can't divide by zero"
    ui.units.setText("0")
    assert ui.result.text() == ""
    assert ui.result.toolTip() == "Can't divide by zero"
    ui.units.setText("2")
    assert ui.result.text() == "$5.00"
    assert ui.result.toolTip() != "Can't divide by zero"
    host.close()


def _block(text: str, start: str) -> str:
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith(start))
    end = first + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("        ")):
        end += 1
    return "\n".join(lines[first:end]).rstrip()


# Reviewed against LOGIC 7.2 and 7.3 by the lead. Connects follow the first refresh
# (CONTRACTS 18.2); the temporary is ``_cbcs_value`` rather than the listing's ``line_total``.
_SCENARIO1_REFRESH = """    def cbcs_refresh(self, *args):
        # rules
        \"\"\"Run every rule on this form again. Safe to call from your own code.\"\"\"
        if self._cbcs_refreshing:
            return
        self._cbcs_refreshing = True
        try:
            # discountEdit: Enabled when  discountCheck
            self.discountEdit.setEnabled(self.discountCheck.isChecked())
        finally:
            self._cbcs_refreshing = False"""

_SCENARIO2_BODY = """            # lineTotalLabel: Value =  qtySpin * priceSpin   (format: money)
            _cbcs_value = self.qtySpin.value() * _cbcs_dec(self.priceSpin.value(), 2)
            self.lineTotalLabel.setText(_cbcs_money(_cbcs_value))"""

_SCENARIO2_SETUP = """    def _cbcs_setup(self, Invoice):
        self._form = Invoice
        self._cbcs_refreshing = False
        self.cbcs_refresh()
        self.qtySpin.valueChanged.connect(self.cbcs_refresh)
        self.priceSpin.valueChanged.connect(self.cbcs_refresh)"""


def test_scenario_blocks_are_exact(tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    _doc, one = _load(_scenario1(), "invoice", tmp_path / "one")
    assert _block(one.text or "", "def cbcs_refresh") == _SCENARIO1_REFRESH
    _doc, two = _load(_scenario2(), "invoice", tmp_path / "two")
    assert _SCENARIO2_BODY in (two.text or "")
    assert _block(two.text or "", "def _cbcs_setup") == _SCENARIO2_SETUP
