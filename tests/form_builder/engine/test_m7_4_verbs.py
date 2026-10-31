# pyright: reportAttributeAccessIssue=false
"""M7.4 verbs, when, and scenario 4 (LOGIC_DESIGN 7.5, CONTRACTS 18.4)."""

from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path
from typing import Any, List

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_steps, write_steps
from app.features.form_builder.engine.logic.events_catalog import step_words
from app.features.form_builder.engine.logic.events_codec import read_list
from app.features.form_builder.engine.logic.verbs import default_registry
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.test_m6_1a_events import form

pytestmark = pytest.mark.unit

_VERBS = (
    "validate",
    "set",
    "clear",
    "focus",
    "enable",
    "disable",
    "show",
    "hide",
    "message",
    "ask",
    "stop",
    "page",
    "openForm",
    "close",
    "call",
    "slot",
)


def _step(payload: dict) -> Any:
    parsed = read_list(json.dumps([payload]))
    assert parsed.error is None, parsed.error
    return parsed.steps[0]


def _round_trip(payload: dict) -> Any:
    text = json.dumps([payload])
    read = parse_steps(text)
    assert read.error is None, read.error
    again = parse_steps(write_steps(read.steps))
    assert again.error is None
    assert again.steps[0].verb == read.steps[0].verb
    assert again.steps[0].when == read.steps[0].when
    assert again.steps[0].fields == read.steps[0].fields
    event = read_list(write_steps(read.steps))
    assert event.error is None, event.error
    return event.steps[0]


def generate(text: str, tmp_path: Path) -> str:
    path = tmp_path / "sale.ui"
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_sale.py"),
        window_path=str(tmp_path / "sale_window.py"),
        module_name="ui_sale",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    return result.text


def _form(*steps: Any, sender: str = "clearButton") -> str:
    extra = (
        '  <widget class="QPushButton" name="saveButton"/>\n'
        '  <widget class="QStackedWidget" name="detailTabs">\n'
        '   <widget class="QWidget" name="shippingPage"/>\n'
        "  </widget>\n"
    )
    log = open_log(form(extra_widgets=extra))
    log.execute(SetEventSteps(sender, "clicked", steps))
    return saved(log.document)


def _load(source: str, calls: List[Any], answers: Any = None, boxes: Any = None) -> Any:
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([])
    del app
    namespace: Any = types.ModuleType("generated_m74")
    exec(compile(source, "ui_sale.py", "exec"), namespace.__dict__)
    if boxes is not None:
        namespace.QMessageBox = boxes
    answers = answers if answers is not None else {}

    class Window(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = namespace.Ui_Sale()
            self.ui.setupUi(self)

        def save_invoice(self) -> Any:
            calls.append("save_invoice")
            return answers.get("save_invoice")

        def __getattr__(self, name: str) -> Any:
            if name.startswith("m_"):
                def method(*args: Any) -> Any:
                    calls.append((name, args))
                    return answers.get(name)

                return method
            raise AttributeError(name)

    return Window()


@pytest.mark.parametrize("name", _VERBS)
def test_every_m7_verb_is_one_registry_entry(name: str) -> None:
    spec = default_registry().get(name)
    assert spec is not None and spec.name == name
    assert spec.words and spec.emit and spec.validate


@pytest.mark.parametrize(
    "payload, words",
    [
        ({"do": "validate"}, "Check all fields (stops here if a field fails)"),
        ({"do": "set", "field": "nameEdit", "formula": "1"}, "Set nameEdit to 1"),
        ({"do": "clear", "fields": ["nameEdit"]}, "Clear nameEdit"),
        ({"do": "focus", "field": "phoneEdit"}, "Move focus to phoneEdit"),
        ({"do": "enable", "field": "nameEdit"}, "Enable nameEdit"),
        ({"do": "disable", "field": "nameEdit"}, "Disable nameEdit"),
        ({"do": "show", "field": "nameEdit"}, "Show nameEdit"),
        ({"do": "hide", "field": "nameEdit"}, "Hide nameEdit"),
        ({"do": "message", "level": "info", "text": "Saved."}, 'Show a message u"Saved."'),
        ({"do": "ask", "text": "Delete this line?"}, 'Ask u"Delete this line?" (stops here on No)'),
        ({"do": "stop", "when": "1 = 1", "message": "No"}, "Stop here if 1 = 1"),
        ({"do": "page", "field": "detailTabs", "page": "shippingPage"}, "Switch detailTabs to shippingPage"),
        ({"do": "openForm", "form": "customer", "mode": "dialog"}, "Open customer"),
        ({"do": "close", "result": "accept"}, "Accept (OK)"),
        ({"do": "call", "method": "save_invoice"}, "Call save_invoice()"),
        ({"do": "slot", "target": "nameEdit", "slot": "clear()"}, "Clear nameEdit"),
    ],
)
def test_verb_round_trip_and_words(payload: dict, words: str) -> None:
    step = _round_trip(payload)
    assert step_words(step, payload.get("field") or payload.get("target") or "Sale") == words


def test_scenario_4_checks_then_calls_and_stops_when_invalid(tmp_path: Path, qapp: Any) -> None:
    del qapp
    steps = (_step({"do": "validate"}), _step({"do": "call", "method": "save_invoice"}))
    source = generate(_form(*steps, sender="saveButton"), tmp_path)
    ast.parse(source, feature_version=(3, 9))
    assert "if not self.cbcs_validate():" in source
    assert "return" in source
    assert "self._form.save_invoice()" in source
    assert "if self._form.save_invoice() is False:" not in source
    calls: List[Any] = []
    win = _load(source, calls)
    win.ui.cbcs_validate = lambda: False
    win.ui.saveButton.click()
    assert calls == []
    win.ui.cbcs_validate = lambda: True
    win.ui.saveButton.click()
    assert calls == ["save_invoice"]


def test_a_later_message_wraps_the_call_the_m6_way(tmp_path: Path) -> None:
    steps = (
        _step({"do": "validate"}),
        _step({"do": "call", "method": "save_invoice"}),
        _step({"do": "message", "level": "info", "text": "Saved."}),
    )
    source = generate(_form(*steps, sender="saveButton"), tmp_path)
    assert "if self._form.save_invoice() is False:" in source
    assert 'QMessageBox.information(self._form, u"", u"Saved.")' in source


@pytest.mark.parametrize(
    "when, present",
    [
        ("not is_blank(0)", "if not _cbcs_is_blank(0):"),
        ("is_blank(0)", "if _cbcs_is_blank(0):"),
    ],
)
def test_when_wraps_one_step(when: str, present: str, tmp_path: Path) -> None:
    source = generate(_form(_step({"do": "slot", "target": "nameEdit", "slot": "clear()", "when": when})), tmp_path)
    assert present in source
    assert "self.nameEdit.clear()" in source
    ast.parse(source, feature_version=(3, 9))


def test_a_when_with_an_error_skips_only_that_step(tmp_path: Path, qapp: Any) -> None:
    del qapp
    steps = (
        _step({"do": "slot", "target": "nameEdit", "slot": "clear()", "when": "@@@"}),
        _step({"do": "slot", "target": "phoneEdit", "slot": "clear()"}),
    )
    source = generate(_form(*steps), tmp_path)
    assert "# step 1 skipped (" in source and "see Problems)" in source
    assert "nameEdit.clear" not in source
    assert "self.phoneEdit.clear()" in source
    win = _load(source, [])
    win.ui.phoneEdit.setText("stay")
    win.ui.nameEdit.setText("kept")
    win.ui.clearButton.click()
    assert win.ui.phoneEdit.text() == ""
    assert win.ui.nameEdit.text() == "kept"


def _drop_imported_forms() -> None:
    """A cached ``forms`` package from an earlier test hides this test's package."""
    for name in list(sys.modules):
        if name == "forms" or name.startswith("forms."):
            sys.modules.pop(name, None)


def test_each_verb_emits_and_runs(tmp_path: Path, qapp: Any) -> None:
    del qapp
    from PySide6 import QtWidgets
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    saved_box = QtWidgets.QMessageBox

    (tmp_path / "customer.ui").write_text("<ui/>", encoding="utf-8")
    forms = tmp_path / "pkg"
    package = forms / "forms"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "customer_window.py").write_text(
        "from PySide6.QtWidgets import QDialog\n"
        "class CustomerWindow(QDialog):\n"
        "    seen = False\n"
        "    def exec(self):\n"
        "        CustomerWindow.seen = True\n"
        "        self.show()\n"
        "        return 1\n"
        "    def show(self):\n"
        "        CustomerWindow.seen = True\n"
        "        return super().show()\n",
        encoding="utf-8",
    )
    _drop_imported_forms()
    sys.path.insert(0, str(forms))
    seen: List[str] = []

    class _Box:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def information(*_args: Any) -> None:
            seen.append("info")

        @staticmethod
        def question(*_args: Any) -> object:
            seen.append("ask")
            return QMessageBox.StandardButton.Yes

    steps = (
        _step({"do": "set", "field": "nameEdit", "formula": '"Hi"'}),
        _step({"do": "focus", "field": "phoneEdit"}),
        _step({"do": "enable", "field": "giftCheck"}),
        _step({"do": "show", "field": "nameEdit"}),
        _step({"do": "message", "text": "Saved."}),
        _step({"do": "clear", "fields": ["nameEdit"]}),
        _step({"do": "disable", "field": "giftCheck"}),
        _step({"do": "hide", "field": "phoneEdit"}),
        _step({"do": "page", "field": "detailTabs", "page": "shippingPage"}),
        _step({"do": "ask", "text": "Go on?"}),
        _step({"do": "stop", "when": "is_blank(0)", "message": "nope"}),
        _step({"do": "openForm", "form": "customer", "mode": "dialog"}),
        _step({"do": "call", "method": "m_done"}),
        _step({"do": "slot", "target": "qtySpin", "slot": "selectAll()"}),
        _step({"do": "close", "result": "accept"}),
    )
    source = generate(_form(*steps), tmp_path)
    ast.parse(source, feature_version=(3, 9))
    for fragment in (
        "_cbcs_value = 'Hi'",
        'self.nameEdit.setText("" if _cbcs_value is None else _cbcs_value)',
        "self.phoneEdit.setFocus()",
        "self.giftCheck.setEnabled(True)",
        "self.nameEdit.show()",
        "QMessageBox.information",
        'self.nameEdit.setText(u"")',
        "self.giftCheck.setEnabled(False)",
        "self.phoneEdit.hide()",
        "self.detailTabs.setCurrentWidget(self.shippingPage)",
        "QMessageBox.question",
        "from forms.customer_window import CustomerWindow",
        "self._form.m_done()",
        "self.qtySpin.selectAll()",
        "self._form.accept()",
    ):
        assert fragment in source, fragment
    calls: List[Any] = []
    win = None
    try:
        win = _load(source, calls, boxes=_Box)
        win.ui.giftCheck.setEnabled(False)
        win.ui.nameEdit.hide()
        win.ui.clearButton.click()
        assert win.ui.nameEdit.text() == ""
        assert not win.ui.giftCheck.isEnabled()
        assert not win.ui.phoneEdit.isVisible()
        assert calls == [("m_done", ())]
        assert win.result() == QDialog.DialogCode.Accepted
        assert "info" in seen and "ask" in seen
        import importlib

        customer_window = importlib.import_module("forms.customer_window")
        assert customer_window.CustomerWindow.seen is True
    finally:
        if win is not None:
            win.close()
        app = QApplication.instance()
        if app is not None:
            for widget in list(app.topLevelWidgets()):
                if type(widget).__name__ == "CustomerWindow":
                    widget.close()
                    widget.deleteLater()
        if str(forms) in sys.path:
            sys.path.remove(str(forms))
        _drop_imported_forms()
        QtWidgets.QMessageBox = saved_box


def test_ask_no_stops_the_list(tmp_path: Path, qapp: Any) -> None:
    del qapp

    from PySide6.QtWidgets import QMessageBox

    class _Box:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def question(*_args: Any) -> object:
            return QMessageBox.StandardButton.No

    source = generate(
        _form(
            _step({"do": "ask", "text": "Go on?"}),
            _step({"do": "slot", "target": "nameEdit", "slot": "clear()"}),
        ),
        tmp_path,
    )
    win = _load(source, [], boxes=_Box)
    win.ui.nameEdit.setText("stay")
    win.ui.clearButton.click()
    assert win.ui.nameEdit.text() == "stay"


def test_open_form_that_does_not_generate_is_fb120(tmp_path: Path) -> None:
    source = generate(_form(_step({"do": "openForm", "form": "missing", "mode": "dialog"})), tmp_path)
    assert "# step 1 skipped (FB120: see Problems)" in source
    assert "import" not in source.split("def _cbcs_clearButton_clicked", 1)[1].split("def ", 1)[0]
    read = read_ui(_form(_step({"do": "openForm", "form": "missing", "mode": "dialog"})), allocator=IdAllocator())
    path = tmp_path / "sale.ui"
    result = generate_form_module(
        read.document,
        scope=FormScope(kind="project", ui_path=str(path), project_root=str(tmp_path), generated_path=str(tmp_path / "ui_sale.py"), window_path="", module_name="ui_sale"),
        source_bytes=b"<ui/>",
    )
    assert any(item.code == "FB120" for item in result.diagnostics)


def test_one_off_enable_warns_when_a_rule_controls_it(tmp_path: Path) -> None:
    text = form().replace(
        '<widget class="QLineEdit" name="nameEdit"/>',
        '<widget class="QLineEdit" name="nameEdit">'
        '<property name="cbcsEnabledWhen" stdset="0"><string>discountCheck</string></property>'
        "</widget>",
    )
    log = open_log(text)
    log.execute(SetEventSteps("clearButton", "clicked", (_step({"do": "enable", "field": "nameEdit"}),)))
    source_text = saved(log.document)
    source = generate(source_text, tmp_path)
    assert "self.nameEdit.setEnabled(True)" in source
    read = read_ui(source_text, allocator=IdAllocator())
    result = generate_form_module(
        read.document,
        scope=FormScope(
            kind="project",
            ui_path=str(tmp_path / "sale.ui"),
            project_root=str(tmp_path),
            generated_path=str(tmp_path / "ui_sale.py"),
            window_path="",
            module_name="ui_sale",
        ),
        source_bytes=source_text.encode("utf-8"),
    )
    assert any(item.code == "FB117" and item.fixes[0].title == "Show the rule" for item in result.diagnostics)


def test_opened_is_the_last_setup_line_and_closing_uses_the_guard(tmp_path: Path, qapp: Any) -> None:
    del qapp
    text = form(
        extra_root=(
            '<property name="cbcsOnOpened" stdset="0"><string>'
            + json.dumps([{"do": "set", "field": "nameEdit", "formula": '"open"'}])
            + "</string></property>"
            '<property name="cbcsOnClosing" stdset="0"><string>'
            + json.dumps([{"do": "stop", "when": "not is_blank(0)"}])
            + "</string></property>"
        )
    )
    source = generate(text, tmp_path)
    chunk = source.split("def _cbcs_setup", 1)[1]
    rest = chunk.splitlines()[1:]
    lines = []
    for line in rest:
        if line and not line.startswith(" "):
            break
        lines.append(line)
    body = [line for line in lines if line.strip()]
    assert body[-1].strip() == "self._cbcs_Sale_opened()"
    assert "class _CbcsCloseGuard(QObject):" in chunk
    assert "self.ui._cbcs_Sale_closing() is not True" in chunk
    assert ".opened.connect" not in source
    win = _load(source, [])
    assert win.ui.nameEdit.text() == "open"
    win.show()
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()
    QCoreApplication.sendEvent(win, event)
    assert win.isVisible()
    assert not event.isAccepted()


def test_a_blank_set_or_message_never_shows_none(tmp_path: Path, qapp: Any) -> None:
    del qapp

    from PySide6.QtWidgets import QMessageBox

    shown: List[str] = []

    class _Box:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def information(_parent: Any, _title: str, text: str) -> None:
            shown.append(text)

    source = generate(
        _form(
            _step({"do": "set", "field": "qtySpin", "formula": "whole(1 / 0)"}),
            _step({"do": "message", "formula": "nameEdit"}),
        ),
        tmp_path,
    )
    win = _load(source, [], boxes=_Box)
    win.ui.qtySpin.setValue(win.ui.qtySpin.minimum() + 5)
    win.ui.nameEdit.setText("")
    win.ui.clearButton.click()
    assert "# step" not in source.split("def _cbcs_clearButton_clicked", 1)[1].split("def ", 1)[0]
    assert win.ui.qtySpin.value() == win.ui.qtySpin.minimum()
    assert shown == [""]
