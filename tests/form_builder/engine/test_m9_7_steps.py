# pyright: reportAttributeAccessIssue=false
"""M9.7 step lists stop on a failed record step, and openForm opens the target."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, List

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.test_m6_1a_events import form
from tests.form_builder.engine.test_m7_4_verbs import _form, _step, generate

import app.features.form_builder.engine.diagnostic_codes.fb1xx_formula  # noqa: F401

pytestmark = pytest.mark.unit

_STOPS = (
    "new",
    "save",
    "delete",
    "revert",
    "reload",
    "first",
    "previous",
    "next",
    "last",
)


def _ui(class_name: str, root: str = "QDialog") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>%s</class>\n"
        ' <widget class="%s" name="%s"/>\n'
        " <resources/>\n"
        " <connections/>\n"
        "</ui>\n" % (class_name, root, class_name)
    )


def _handler(source: str, sender: str = "clearButton") -> str:
    chunk = source.split("def _cbcs_%s_clicked" % sender, 1)[1]
    lines = []
    for line in chunk.splitlines()[1:]:
        if line.startswith("    def ") or (line and not line.startswith(" ")):
            break
        lines.append(line)
    return "\n".join(lines)


def _result(text: str, tmp_path: Path) -> Any:
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
    return generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))


def _open(tmp_path: Path, step: dict, *, stem: str = "customer", class_name: str = "Customer", root: str = "QDialog", source: str = "") -> str:
    (tmp_path / ("%s.ui" % stem)).write_text(_ui(class_name, root), encoding="utf-8")
    text = source or _form(_step(step))
    result = _result(text, tmp_path)
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    ast.parse(result.text, feature_version=(3, 9))
    return result.text


class _Box:
    def __init__(self, calls: List[str]) -> None:
        self._calls = calls

    def information(self, *_args: Any) -> None:
        self._calls.append("message")


def _run(source: str, method: str, owner: Any, calls: List[str]) -> None:
    namespace = {}  # type: dict
    exec(compile(source, "ui_sale.py", "exec"), namespace)  # noqa: S102
    namespace["QMessageBox"] = _Box(calls)
    ui_name = next(name for name in namespace if name.startswith("Ui_"))
    getattr(namespace[ui_name], method)(owner)


class _Record:
    def __init__(self, result: bool, calls: List[str]) -> None:
        self._result = result
        self.calls = calls
        self._form = None

    def __getattr__(self, name: str) -> Any:
        if not name.startswith("cbcs_"):
            raise AttributeError(name)

        def run(*_args: Any) -> bool:
            self.calls.append(name)
            return self._result

        return run


def _save_then_message_then_next(tmp_path: Path) -> str:
    source = generate(
        _form(
            _step({"do": "save"}),
            _step({"do": "message", "level": "info", "text": "Saved."}),
            _step({"do": "next"}),
            sender="saveButton",
        ),
        tmp_path,
    )
    ast.parse(source, feature_version=(3, 9))
    return source


def test_save_returning_false_stops_the_list(tmp_path: Path) -> None:
    calls: List[str] = []
    _run(
        _save_then_message_then_next(tmp_path),
        "_cbcs_saveButton_clicked",
        _Record(False, calls),
        calls,
    )
    assert calls == ["cbcs_save"]


def test_save_returning_true_continues_the_list(tmp_path: Path) -> None:
    calls: List[str] = []
    _run(
        _save_then_message_then_next(tmp_path),
        "_cbcs_saveButton_clicked",
        _Record(True, calls),
        calls,
    )
    assert calls == ["cbcs_save", "message", "cbcs_next"]


@pytest.mark.parametrize("verb", _STOPS)
def test_a_false_record_step_stops_before_the_message(verb: str, tmp_path: Path) -> None:
    source = generate(
        _form(_step({"do": verb}), _step({"do": "message", "level": "info", "text": "Saved."})),
        tmp_path,
    )
    calls: List[str] = []
    _run(source, "_cbcs_clearButton_clicked", _Record(False, calls), calls)
    assert calls == ["cbcs_%s" % verb]


def test_open_form_reads_a_spin_box_key_through_the_ui(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog", "key": "qtySpin"},
    )
    body = _handler(source)
    assert "_cbcs_customer.ui.cbcs_open(self.qtySpin.value())" in body
    assert "currentData" not in body


def test_open_form_reads_a_line_edit_as_text(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog", "key": "nameEdit"},
    )
    body = _handler(source)
    assert "_cbcs_customer.ui.cbcs_open(self.nameEdit.text())" in body
    assert "currentData" not in body


def test_open_form_reads_a_lookup_combo_as_item_data(tmp_path: Path) -> None:
    text = form().replace(
        '<widget class="QComboBox" name="customerCombo"/>',
        '<widget class="QComboBox" name="customerCombo">'
        '<property name="cbcsLookup" stdset="0"><string notr="true">'
        '{"table": "customers", "key": "id", "show": "name"}'
        "</string></property></widget>",
    )
    log = open_log(text)
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (_step({"do": "openForm", "form": "customer", "mode": "dialog", "key": "customerCombo"}),),
        )
    )
    source = _open(tmp_path, {}, source=saved(log.document))
    body = _handler(source)
    assert "_cbcs_customer.ui.cbcs_open(self.customerCombo.currentData())" in body


def test_open_form_reads_combo_item_data(tmp_path: Path) -> None:
    text = form().replace(
        '<widget class="QComboBox" name="customerCombo"/>',
        '<widget class="QComboBox" name="customerCombo">'
        '<item><property name="text"><string>Ada</string></property>'
        '<property name="userData"><string>7</string></property></item>'
        "</widget>",
    )
    log = open_log(text)
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (_step({"do": "openForm", "form": "customer", "mode": "dialog", "key": "customerCombo"}),),
        )
    )
    source = _open(tmp_path, {}, source=saved(log.document))
    body = _handler(source)
    assert "_cbcs_customer.ui.cbcs_open(self.customerCombo.currentData())" in body


def test_open_form_imports_the_class_stored_in_the_ui(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog"},
        class_name="ClientEditor",
    )
    body = _handler(source)
    assert "from forms.customer_window import ClientEditorWindow" in body
    assert "CustomerWindow" not in body


def test_refresh_lookups_runs_after_the_dialog_closes(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog", "then": "refreshLookups"},
    )
    body = _handler(source)
    assert "self.cbcs_load_lookups()" in body
    assert body.index(".exec()") < body.index("self.cbcs_load_lookups()")
    assert "# then" not in body


def test_another_then_value_is_left_out(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog", "then": "doSomething"},
    )
    body = _handler(source)
    assert "doSomething" not in body
    assert "cbcs_load_lookups" not in body


def test_window_mode_asks_before_show(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "window"},
    )
    shown = _run_open_handler(_handler(source), leave=None)
    assert shown == ["show"]
    assert _run_open_handler(_handler(source), leave=False) == []
    assert _run_open_handler(_handler(source), leave=True) == ["show"]


def _run_open_handler(body: str, leave: Any) -> List[str]:
    """Run the generated handler with a stand-in window class; return what it called."""

    import sys
    import textwrap
    import types

    calls = []  # type: List[str]

    class CustomerWindow:
        def __init__(self, _parent: object) -> None:
            pass

        def show(self) -> None:
            calls.append("show")

        def exec(self) -> None:
            calls.append("exec")

    class Host:
        _form = object()

    host = Host()
    if leave is not None:
        setattr(host, "_cbcs_confirm_leave", lambda: leave)
    package = types.ModuleType("forms")
    module = types.ModuleType("forms.customer_window")
    setattr(module, "CustomerWindow", CustomerWindow)
    saved_modules = {name: sys.modules.get(name) for name in ("forms", "forms.customer_window")}
    sys.modules["forms"] = package
    sys.modules["forms.customer_window"] = module
    try:
        scope = {}  # type: dict
        exec("def handler(self):\n" + textwrap.indent(textwrap.dedent(body), "    ") + "\n    pass\n", scope)
        scope["handler"](host)
    finally:
        for name, old_module in saved_modules.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module
    return calls


def test_dialog_mode_does_not_ask_about_unsaved_changes(tmp_path: Path) -> None:
    source = _open(
        tmp_path,
        {"do": "openForm", "form": "customer", "mode": "dialog"},
    )
    body = _handler(source)
    assert "_cbcs_confirm_leave" not in body
    assert ".exec()" in body


def test_a_main_window_cannot_open_as_a_dialog(tmp_path: Path) -> None:
    (tmp_path / "ledger.ui").write_text(_ui("Ledger", "QMainWindow"), encoding="utf-8")
    text = _form(_step({"do": "openForm", "form": "ledger", "mode": "dialog"}))
    result = _result(text, tmp_path)
    assert result.text is not None
    body = _handler(result.text)
    hits = [item for item in result.diagnostics if item.code == "FB121"]
    assert len(hits) == 1
    assert hits[0].severity == Severity.ERROR
    assert hits[0].message == (
        "ledger is not a dialog, so Open as a dialog cannot run it. "
        "Open it as a window, or make the form a dialog."
    )
    assert ".exec()" not in body
    assert CODES["FB121"].severity == Severity.ERROR
    assert "not a dialog" in CODES["FB121"].title


def test_an_unreadable_target_file_keeps_the_stem_class(tmp_path: Path) -> None:
    # The verb runner plants ``<ui/>`` so a hand-written window module can load.
    # A file that is present but not a form is not "missing" (FB120).
    (tmp_path / "customer.ui").write_text("<ui/>", encoding="utf-8")
    text = _form(_step({"do": "openForm", "form": "customer", "mode": "dialog"}))
    result = _result(text, tmp_path)
    assert result.text is not None
    body = _handler(result.text)
    assert "from forms.customer_window import CustomerWindow" in body
    assert not any(item.code == "FB120" for item in result.diagnostics)
