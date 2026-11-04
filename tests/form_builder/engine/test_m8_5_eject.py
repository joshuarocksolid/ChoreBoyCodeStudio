# pyright: reportAttributeAccessIssue=false, reportMissingImports=false
"""Eject to code matches the bound form, and undo restores both files."""

from __future__ import annotations

import ast
import os
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.eject import (
    EjectPlan,
    ejected_method,
    method_line,
    plan_eject,
    splice_window,
    window_edit,
)
from app.features.form_builder.engine.codegen.window_template import render_window_class
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_lookup
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.checks import Length, write_checks
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_ui
from app.qt.QtWidgets import QApplication, QDialog
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class, _xml
from tests.form_builder.engine.test_m8_3b_lines import _ROWS, _invoice_schema, _prepare, _rows_xml
from tests.form_builder.engine.test_m8_3c_list import _prepare as _prepare_list
from tests.form_builder.engine.test_m8_3c_list import _source, _widgets
from xml.sax.saxutils import escape

pytestmark = pytest.mark.unit


def test_ejected_invoice_matches_the_bound_form(tmp_path: Path) -> None:
    bound = _invoice_run(tmp_path / "bound", ejected=False)
    ejected = _invoice_run(tmp_path / "ejected", ejected=True)
    assert ejected.sql == bound.sql
    assert ejected.fields == bound.fields
    assert ejected.lines == bound.lines
    assert ejected.after_find == bound.after_find
    assert ejected.saved_lines == bound.saved_lines
    assert ejected.after_delete == bound.after_delete
    assert bound.after_delete == 0
    assert len(bound.saved_lines) == len(bound.lines) + 1


def test_ejected_list_matches_the_bound_list(tmp_path: Path) -> None:
    bound = _list_run(tmp_path / "bound", ejected=False)
    ejected = _list_run(tmp_path / "ejected", ejected=True)
    assert ejected.sql == bound.sql
    assert ejected.names == bound.names
    assert ejected.opened == bound.opened
    assert bound.opened


def test_undo_restores_the_form_and_the_window_file(tmp_path: Path) -> None:
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        before = session.text()
        document = read_ui(before, allocator=IdAllocator()).document
        plan = plan_eject(document, scope)
        window = render_window_class(document, scope=scope)
        edited = splice_window(window, plan)
        assert "def load_record(" in edited
        assert "return self.ui.cbcs_open(" not in edited
        assert "def _cbcs_bind_ejected" not in edited
        assert "import cbcs_connections" in edited
        assert "from cbcs_connections import" not in edited
        assert "\n    # record\n" not in edited
        assert 'u"' not in edited
        assert "getattr(self, \"load_lookups\"" not in edited
        assert "self.load_lookups()" in edited
        assert " as _conn" not in edited
        assert " as conn:" in edited
        assert _leading_underscore_locals(edited) == []
        assert "'SELECT \"id\"" in edited
        write = edited.split("def write_fields(", 1)[1].split("\ndef ", 1)[0]
        assert write.count("invoiceNoEdit.setText") == 1
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        assert session.log.undo_label() == "Eject to code"
        assert session.log.undo() is True
        assert session.text() == before
        edit = window_edit(window, plan)
        applied = window[: edit.start] + edit.text + window[edit.end :]
        assert applied == edited
    finally:
        set_schema_reader(None)


def test_rewired_save_calls_save_record(tmp_path: Path) -> None:
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        plan = plan_eject(session.document, scope)
        assert plan.first_method == "load_record"
        assert "save_record" in plan.method_names
        assert "add_line" in plan.method_names
        assert plan.summary[1] == "Removes the data settings from invoice.ui"
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        methods = [step.method for state in read_events(session.document) for step in state.steps if step.method]
        assert methods == ["save_record"]
        assert "Adds " in plan.summary[0]
        assert "helpers" in plan.summary[0]
        assert ejected_method(session.document) == "load_record"
        result = generate_form_module(
            read_ui(session.text(), allocator=IdAllocator()).document,
            scope=scope,
            source_bytes=session.text().encode("utf-8"),
        )
        assert result.text is not None
        assert "def cbcs_save" not in result.text
        assert "save_record" in result.text
    finally:
        set_schema_reader(None)


def _close_leftovers() -> None:
    """Close forms an earlier test left up, before this run records SQL."""

    app = QApplication.instance()
    if app is None:
        return
    from app.qt.QtCore import QTimer

    for timer in app.findChildren(QTimer):
        timer.stop()
    for widget in list(app.topLevelWidgets()):
        widget.deleteLater()
    app.processEvents()


def _drop_forms(root: Path) -> None:
    inserted = str(root)
    if sys.path and sys.path[0] == inserted:
        sys.path.pop(0)
    for name in list(sys.modules):
        if name == "forms" or name.startswith("forms."):
            sys.modules.pop(name, None)


def _scenario_ui() -> str:
    lookup = (
        '    <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>\n'
        % escape(write_lookup(Lookup("customers", "id", "name", "name")))
    )
    return _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QComboBox", "customerCombo", "customer_id", lookup),
            ("QTableView", "linesView", "", _rows_xml(_ROWS)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )


class _Outcome:
    def __init__(
        self,
        sql: Sequence[str],
        fields: Tuple[Any, ...],
        lines: Sequence[Any],
        after_find: Tuple[Any, ...],
        saved_lines: Sequence[Any],
        after_delete: int,
    ) -> None:
        self.sql = tuple(sql)
        self.fields = fields
        self.lines = tuple(lines)
        self.after_find = after_find
        self.saved_lines = tuple(saved_lines)
        self.after_delete = after_delete


def _invoice_run(tmp_path: Path, *, ejected: bool) -> _Outcome:
    module = None
    root: Optional[Path] = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        sql: List[str] = []
        _close_leftovers()
        module = _connections(root, sql)
        choose = lambda text: "Delete" if text.startswith("Delete this") else "Close"  # noqa: E731
        if ejected:
            plan = plan_eject(session.document, scope)
            with session.log.transaction("Eject to code"):
                for command in plan.commands:
                    session.log.execute(command)
            host = _host_ejected(root, scope, session.text(), plan, module, choose)
            ui = host.ui
            save, delete, add, find = host.save_record, host.delete_record, host.add_line, host.find_record
            lines_owner = host
        else:
            host = _host_bound(root, scope, session.text(), module, choose)
            ui = host.ui
            save, delete, add, find = ui.cbcs_save, ui.cbcs_delete, ui._cbcs_add_row, ui.cbcs_find
            lines_owner = ui
        fields = (ui.invoiceNoEdit.text(), ui.customerCombo.currentText())
        lines = _line_values(lines_owner)
        find()
        after_find = (ui.invoiceNoEdit.text(), ui.customerCombo.currentText())
        add()
        _set_product(lines_owner, 1)
        assert save() is True
        saved = _rows(root, "SELECT product_id, description, qty, price, needed FROM invoice_lines ORDER BY line_no")
        assert delete() is True
        after_delete = _count(root, "SELECT COUNT(*) FROM invoices")
        host.close()
        module.close_all()
        return _Outcome(sql, fields, lines, after_find, saved, after_delete)
    finally:
        if module is not None:
            _restore_connections(module)
        set_schema_reader(None)
        if root is not None:
            _drop_forms(root)


class _ListOutcome:
    def __init__(self, sql: Sequence[str], names: Sequence[str], opened: Sequence[Any]) -> None:
        self.sql = tuple(sql)
        self.names = tuple(names)
        self.opened = tuple(opened)


def _list_run(tmp_path: Path, *, ejected: bool) -> _ListOutcome:
    root, scope, ui_text = _project(tmp_path, _xml(_source(10), _widgets()), _prepare_list, "customers.ui", None)
    _write_customer_window(root)
    inserted = str(root)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    for name in ("forms", "forms.customer_window"):
        sys.modules.pop(name, None)
    module = None
    try:
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _close_leftovers()
        sql: List[str] = []
        module = _connections(root, sql)
        if ejected:
            plan = plan_eject(session.document, scope)
            with session.log.transaction("Eject to code"):
                for command in plan.commands:
                    session.log.execute(command)
            host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
            host.ui.customersView.selectRow(0)
            host.open_record("selected")
        else:
            host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
            host.ui.customersView.selectRow(0)
            host.ui.cbcs_open_record("selected")
        model = host.ui.customersView.model()
        names = [model.item(row, 0).text() for row in range(model.rowCount())]
        import forms.customer_window as window_mod

        opened = list(window_mod.CustomerWindow.opened)
        host.close()
        module.close_all()
        return _ListOutcome(sql, names, opened)
    finally:
        if module is not None:
            _restore_connections(module)
        if sys.path and sys.path[0] == inserted:
            sys.path.pop(0)
        for name in ("forms", "forms.customer_window"):
            sys.modules.pop(name, None)


def _project(
    tmp_path: Path, ui_text: str, prepare: Callable[[Path], Path], filename: str, schema: Any
) -> Tuple[Path, FormScope, str]:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / filename
    ui_path.write_text(ui_text, encoding="utf-8")
    prepare(root)
    value = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),))
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m85"), encoding="utf-8")
    if schema is not None:
        folder = root / "cbcs" / "schema"
        folder.mkdir(parents=True)
        (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
        install_schema_reader(str(root))
    stem = ui_path.stem
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(forms / ("ui_%s.py" % stem)),
        window_path=str(forms / ("%s_window.py" % stem)),
        module_name="forms.ui_%s" % stem,
    )
    return root, scope, ui_text


class _TracingCursor:
    def __init__(self, inner: Any, sql: List[str], token: Optional[object] = None) -> None:
        self._inner = inner
        self._sql = sql
        del token

    def execute(self, statement: str, params: Sequence[Any] = ()) -> Any:
        self._sql.append(statement)
        return self._inner.execute(statement, params)

    def executemany(self, statement: str, seq: Any) -> Any:
        self._sql.append(statement)
        return self._inner.executemany(statement, seq)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _TracingConnection:
    def __init__(self, inner: Any, sql: List[str], token: Optional[object] = None) -> None:
        self._inner = inner
        self._sql = sql
        self._token = token

    def cursor(self, *args: Any, **kwargs: Any) -> _TracingCursor:
        return _TracingCursor(self._inner.cursor(*args, **kwargs), self._sql, self._token)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _connections(root: Path, sql: List[str]) -> Any:
    module = _load_module(root / "cbcs_connections.py", "cbcs_connections_m85_%s" % root.parent.name)
    real = module.sqlite3.connect
    expected = os.path.abspath(str(root / "data" / "shop.db"))
    token = object()
    module._cbcs_trace_token = token  # type: ignore[attr-defined]

    def connect(path: str, *args: Any, **kwargs: Any) -> Any:
        connection = real(path, *args, **kwargs)
        if os.path.abspath(str(path)) != expected:
            return connection
        return _TracingConnection(connection, sql, token)

    module.sqlite3.connect = connect
    module._cbcs_original_connect = real  # type: ignore[attr-defined]
    return module


def _mark_run(module: Any, connections: Any) -> None:
    token = getattr(connections, "_cbcs_trace_token", None)
    if token is not None:
        module._cbcs_trace_token = token


def _host_bound(root: Path, scope: FormScope, ui_text: str, connections: Any, choose: Callable[[str], str]) -> Any:
    source = _generate(root, Path(scope.ui_path), ui_text)
    generated = Path(scope.generated_path or "")
    generated.write_text(source, encoding="utf-8")
    module = _load_module(generated, "ui_bound_%s" % Path(scope.ui_path).stem)
    _mark_run(module, connections)
    _install_boxes(module, [], None, choose, lambda: ("INV-1", True))
    return _show(module, connections, None)


def _host_ejected(
    root: Path,
    scope: FormScope,
    ui_text: str,
    plan: Any,
    connections: Any,
    choose: Callable[[str], str],
    rewrite: Optional[Callable[[str], str]] = None,
) -> Any:
    import importlib

    source = _generate(root, Path(scope.ui_path), ui_text)
    generated = Path(scope.generated_path or "")
    generated.write_text(source, encoding="utf-8")
    document = read_ui(ui_text, allocator=IdAllocator()).document
    window_text = splice_window(render_window_class(document, scope=scope), plan)
    if rewrite is not None:
        window_text = rewrite(window_text)
    Path(scope.window_path or "").write_text(window_text, encoding="utf-8")
    (root / "forms" / "__init__.py").write_text("", encoding="utf-8")
    inserted = str(root)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    stem = Path(scope.ui_path).stem
    for name in ("forms", "forms.ui_%s" % stem, "forms.%s_window" % stem):
        sys.modules.pop(name, None)
    window_mod = importlib.import_module("forms.%s_window" % stem)
    _mark_run(window_mod, connections)
    _install_boxes(window_mod, [], None, choose, lambda: ("INV-1", True))
    ui_mod = sys.modules.get("forms.ui_%s" % stem)
    if ui_mod is not None:
        _install_boxes(ui_mod, [], None, choose, lambda: ("INV-1", True))
    previous = sys.modules.get("cbcs_connections")
    sys.modules["cbcs_connections"] = connections
    app = QApplication.instance() or QApplication([])
    window_cls = next(
        value
        for name, value in vars(window_mod).items()
        if isinstance(value, type) and name.endswith("Window")
    )
    host = window_cls()
    host.show()
    app.processEvents()
    host._cbcs_previous_connections = previous  # type: ignore[attr-defined]
    return host


def _show(module: Any, connections: Any, ejected: Optional[Tuple[Any, Any]]) -> Any:
    previous = sys.modules.get("cbcs_connections")
    sys.modules["cbcs_connections"] = connections
    app = QApplication.instance() or QApplication([])

    class Host(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = _ui_class(module)()
            if ejected is not None:
                _prelude, holder = ejected
                for name, value in holder.__dict__.items():
                    if name.startswith("_"):
                        continue
                    setattr(self, name, value.__get__(self, Host))
            self.ui.setupUi(self)
            if ejected is not None:
                ejected[0]._cbcs_bind_ejected(self.ui, self)

    host = Host()
    host.show()
    app.processEvents()
    host._cbcs_previous_connections = previous  # type: ignore[attr-defined]
    return host


def _restore_connections(module: Any) -> None:
    original = getattr(module, "_cbcs_original_connect", None)
    if original is not None:
        module.sqlite3.connect = original
    if sys.modules.get("cbcs_connections") is module:
        sys.modules.pop("cbcs_connections", None)


def _arm_save(session: FormSession) -> None:
    raw = Step("save", None, True, (), ())
    with session.log.transaction("Save verb"):
        session.log.execute(SetEventSteps("saveButton", "clicked", (EventStep("save", raw=raw),)))


def _state(owner: Any, name: str) -> Any:
    """Window methods drop the ``_cbcs_`` prefix. The bound Ui still has it."""

    found = getattr(owner, name, None)
    if found is None and name.startswith("_"):
        found = getattr(owner, "_cbcs" + name, None)
    return found


def _line_values(owner: Any) -> List[Tuple[Any, ...]]:
    ui = owner.ui if getattr(owner, "ui", None) is not None and hasattr(owner.ui, "linesView") else owner
    model = ui.linesView.model()
    names = list(_state(owner, "_line_names"))
    role = _state(owner, "_line_role")
    rows = []
    for row in range(model.rowCount()):
        cells = []
        for column, name in enumerate(names):
            item = model.item(row, column)
            cells.append((name, None if item is None else item.data(role)))
        rows.append(tuple(cells))
    return rows


def _set_product(owner: Any, product_id: int) -> None:
    ui = owner.ui if getattr(owner, "ui", None) is not None and hasattr(owner.ui, "linesView") else owner
    model = ui.linesView.model()
    names = list(_state(owner, "_line_names"))
    row = model.rowCount() - 1
    role = _state(owner, "_line_role")
    model.item(row, names.index("product_id")).setData(product_id, role)
    recompute = getattr(owner, "_recompute_lines", None) or getattr(owner, "_cbcs_recompute_lines")
    recompute()
    model.item(row, names.index("qty")).setData(1, role)
    model.item(row, names.index("price")).setData(Decimal("1.50"), role)


def _rows(root: Path, statement: str) -> List[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(root / "data" / "shop.db"))
    try:
        return [tuple(row) for row in connection.execute(statement)]
    finally:
        connection.close()


def _count(root: Path, statement: str) -> int:
    connection = sqlite3.connect(str(root / "data" / "shop.db"))
    try:
        row = connection.execute(statement).fetchone()
    finally:
        connection.close()
    return int(row[0]) if row else 0


def _write_customer_window(root: Path) -> None:
    forms = root / "forms"
    (forms / "__init__.py").write_text("", encoding="utf-8")
    (forms / "customer_window.py").write_text(
        "class _Signal:\n"
        "    def connect(self, fn):\n"
        "        return None\n\n"
        "class CustomerWindow(object):\n"
        "    opened = []\n"
        "    def __init__(self, parent=None):\n"
        "        self.ui = self\n"
        "        self.finished = _Signal()\n"
        "    def cbcs_open(self, key):\n"
        "        CustomerWindow.opened.append(key)\n"
        "    def isVisible(self):\n"
        "        return False\n"
        "    def exec(self):\n"
        "        return 0\n"
        "    def show(self):\n"
        "        return None\n"
        "    def raise_(self):\n"
        "        return None\n"
        "    def activateWindow(self):\n"
        "        return None\n"
        "    def setWindowFlag(self, flag):\n"
        "        return None\n",
        encoding="utf-8",
    )


def test_splice_keeps_user_code_in_place(tmp_path: Path) -> None:
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        plan = plan_eject(session.document, scope)
        own = _WINDOW.replace(
            "        self.ui.setupUi(self)\n",
            "        self.ui.setupUi(self)\n\n    def save_record(self):\n        return 1\n",
        )
        with pytest.raises(ValueError, match="save_record"):
            splice_window(own, plan)
        main = _WINDOW + '\n\nif __name__ == "__main__":\n    print("run")\n'
        spliced = splice_window(main, plan)
        tree = ast.parse(spliced)
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "InvoiceWindow")
        assert any(isinstance(node, ast.FunctionDef) and node.name == "load_record" for node in window.body)
        main_node = next(node for node in tree.body if isinstance(node, ast.If))
        assert main_node.lineno > (window.end_lineno or 0)
        helper = _WINDOW + "\n\nclass Helper:\n    def go(self):\n        return 1\n"
        spliced = splice_window(helper, plan)
        tree = ast.parse(spliced)
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        assert classes == ["InvoiceWindow", "Helper"]
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "InvoiceWindow")
        assert any(isinstance(node, ast.FunctionDef) and node.name == "load_record" for node in window.body)
        decorated = "def deco(cls):\n    return cls\n\n" + _WINDOW.replace(
            "class InvoiceWindow", "@deco\nclass InvoiceWindow", 1
        )
        spliced = splice_window(decorated, plan)
        tree = ast.parse(spliced)
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        assert window.decorator_list
        assert any(isinstance(node, ast.FunctionDef) and node.name == "load_record" for node in window.body)
        tabs = (
            "from PySide6.QtWidgets import QDialog\n"
            "from forms.ui_invoice import Ui_Invoice\n"
            "class InvoiceWindow(QDialog):\n"
            "\tdef __init__(self, parent=None):\n"
            "\t\tsuper().__init__(parent)\n"
            "\t\tself.ui = Ui_Invoice()\n"
            "\t\tself.ui.setupUi(self)"
        )
        spliced = splice_window(tabs, plan)
        ast.parse(spliced)
        assert "\tdef load_record(" in spliced
        comment = _WINDOW.replace(
            "        self.ui.setupUi(self)\n",
            "        # self.ui.setupUi(self)\n        self.ui.setupUi(self)\n",
        )
        spliced = splice_window(comment, plan)
        assert spliced.count("_setup_ejected()") == 1
        assert method_line(
            "# def save_record(\ndef save_record_extra(self):\n    return 1\ndef save_record(self):\n    return 2\n",
            "save_record",
        ) == 4
    finally:
        set_schema_reader(None)


_WINDOW = """from PySide6.QtWidgets import QDialog

from forms.ui_invoice import Ui_Invoice


class InvoiceWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)
"""


def _mark_leave_and_add(source: str) -> str:
    source = _swap_body(source, "confirm_leave", ["self._seen_leave = True", "return False"])
    return _swap_body(source, "add_line", ["self._seen_add = True", "return None"])


def _swap_body(source: str, name: str, statements: Sequence[str]) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name and node.body:
            first = node.body[0].lineno
            last = node.end_lineno or first
            raw = lines[first - 1]
            indent = raw[: len(raw) - len(raw.lstrip(" \t"))]
            replacement = [("%s%s\n" % (indent, statement)) for statement in statements]
            return "".join(lines[: first - 1] + replacement + lines[last:])
    raise AssertionError(name)


def test_close_and_insert_call_the_window_methods(tmp_path: Path) -> None:
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        plan = plan_eject(session.document, scope)
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        sql: List[str] = []
        module = _connections(root, sql)
        host = _host_ejected(
            root,
            scope,
            session.text(),
            plan,
            module,
            lambda _text: "Close",
            rewrite=_mark_leave_and_add,
        )
        host.close()
        assert host._seen_leave is True
        _state(host, "_add_shortcut").activated.emit()
        assert host._seen_add is True
        host.hide()
        host.deleteLater()
        module.close_all()
    finally:
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_rewired_buttons_keep_arguments_and_enabled_when(tmp_path: Path) -> None:
    from xml.sax.saxutils import escape

    from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_lookup
    from tests.form_builder.engine.test_m8_2_scenario import _xml
    from tests.form_builder.engine.test_m8_3b_lines import _ROWS, _rows_xml

    lookup = (
        '    <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>\n'
        % escape(write_lookup(Lookup("customers", "id", "name", "name")))
    )
    enabled = (
        '    <property name="cbcsEnabledWhen" stdset="0"><string notr="true">not form.isNew</string></property>\n'
        '    <property name="cbcsOnClicked" stdset="0"><string notr="true">[{"do": "delete"}]</string></property>\n'
    )
    refresh = (
        '    <property name="cbcsOnClicked" stdset="0"><string notr="true">%s</string></property>\n'
        % escape('[{"do": "refreshLookups", "fields": ["customerCombo"]}]')
    )
    ui = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QComboBox", "customerCombo", "customer_id", lookup),
            ("QTableView", "linesView", "", _rows_xml(_ROWS)),
            ("QPushButton", "saveButton", "", ""),
            ("QPushButton", "deleteButton", "", enabled),
            ("QPushButton", "reloadButton", "", refresh),
        ),
    )
    try:
        root, scope, ui_text = _project(tmp_path, ui, _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        plan = plan_eject(session.document, scope)
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        sql: List[str] = []
        module = _connections(root, sql)
        seen: List[Any] = []

        host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
        original = host.load_lookups

        def load_lookups(fields=None):
            seen.append(fields)
            return original(fields)

        host.load_lookups = load_lookups
        host.ui.reloadButton.click()
        assert seen == [("customerCombo",)]
        host.new_record()
        assert host.ui.deleteButton.isEnabled() is False
        clicked: List[str] = []
        host.delete_record = lambda: clicked.append("delete") or True
        host.ui.deleteButton.click()
        assert clicked == []
        host.load_record()
        assert host.ui.deleteButton.isEnabled() is True
        host.ui.deleteButton.click()
        assert clicked == ["delete"]
        host.close()
        module.close_all()
    finally:
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_commit_eject_undo_redo_and_a_changed_window_refuses(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.form_builder.integration.code_bridge import CodeBridge, ShellPort
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject
    from app.qt.QtWidgets import QWidget

    editor = None
    shell = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        before = session.text()
        document = read_ui(ui_text, allocator=IdAllocator()).document
        window = render_window_class(document, scope=scope)
        path = str(scope.window_path)
        Path(path).write_text(window, encoding="utf-8")
        editor = CodeEditorWidget()
        editor.setPlainText(window)
        shell = QWidget()
        shell.session = session
        shell._workspace_controller = type(
            "C",
            (),
            {"widget_for_path": lambda _self, asked: editor if os.path.abspath(asked) == os.path.abspath(path) else None},
        )()
        shell.code_bridge = CodeBridge(str(root), ShellPort(shell))
        plan = plan_eject(session.document, scope)
        ui_path = str(scope.ui_path)
        before_ui = Path(ui_path).read_bytes()
        before_py = Path(path).read_bytes()
        assert "Eject saves invoice.ui and invoice_window.py." in plan.summary
        assert commit_eject(shell, plan) == ""
        ejected_py = Path(path).read_bytes()
        ejected_ui = Path(ui_path).read_bytes()
        assert ejected_py != before_py
        assert ejected_ui != before_ui
        assert editor.toPlainText().encode("utf-8") == ejected_py
        assert editor.document().isModified() is False
        assert b"def load_record(" in ejected_py
        editor.document().undo()
        assert editor.toPlainText().encode("utf-8") == ejected_py
        assert session.log.undo() is True
        assert Path(path).read_bytes() == before_py
        assert Path(ui_path).read_bytes() == before_ui
        assert editor.toPlainText().encode("utf-8") == before_py
        assert session.text() == before
        assert session.log.redo() is True
        assert Path(path).read_bytes() == ejected_py
        assert Path(ui_path).read_bytes() == ejected_ui
        assert "def load_record(" in editor.toPlainText()
        assert ejected_method(session.document) == "load_record"
        longer = editor.toPlainText() + "\n# edited\n"
        editor.setPlainText(longer)
        assert session.log.undo() is False
        assert editor.toPlainText() == longer
        assert Path(path).read_bytes() == ejected_py
        assert Path(ui_path).read_bytes() == ejected_ui
        assert ejected_method(session.document) == "load_record"
        assert "changed after Eject" in shell._eject_notice
    finally:
        if editor is not None:
            editor.close()
            editor.deleteLater()
        if shell is not None:
            shell.close()
            shell.deleteLater()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        set_schema_reader(None)


def test_commit_eject_opens_a_closed_window_file(tmp_path: Path, qapp: QApplication) -> None:
    assert qapp is QApplication.instance()
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.form_builder.integration.code_bridge import CodeBridge, ShellPort
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject
    from app.qt.QtWidgets import QWidget

    editors = {}
    shell = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        document = read_ui(ui_text, allocator=IdAllocator()).document
        window = render_window_class(document, scope=scope)
        path = str(scope.window_path)
        Path(path).write_text(window, encoding="utf-8")

        def open_file_at_line(asked: str, _line: int, preview: bool = False) -> None:
            editor = CodeEditorWidget()
            editor.setPlainText(Path(asked).read_text(encoding="utf-8"))
            editor.document().setModified(False)
            editors[os.path.abspath(asked)] = editor

        shell = QWidget()
        shell.session = session
        shell._editor_tab_workflow = type("W", (), {"open_file_at_line": staticmethod(open_file_at_line)})()
        shell._workspace_controller = type(
            "C",
            (),
            {"widget_for_path": lambda _self, asked: editors.get(os.path.abspath(asked))},
        )()
        shell.code_bridge = CodeBridge(str(root), ShellPort(shell))
        plan = plan_eject(session.document, scope)
        assert commit_eject(shell, plan) == ""
        assert "def load_record(" in Path(path).read_text(encoding="utf-8")
        assert os.path.abspath(path) not in editors
    finally:
        for opened in editors.values():
            opened.close()
            opened.deleteLater()
        if shell is not None:
            shell.close()
            shell.deleteLater()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        set_schema_reader(None)


def test_validate_then_save_refuses_a_short_value(tmp_path: Path) -> None:
    from app.features.form_builder.engine.commands.catalog import SetLogic

    module = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        node = session.document.by_name("invoiceNoEdit")[0]
        checks = write_checks((Length(6, None, "Too short"),))
        raw_validate = Step("validate", None, True, (), ())
        raw_save = Step("save", None, True, (), ())
        with session.log.transaction("Checks"):
            session.log.execute(SetLogic(node, "cbcsValidate", checks))
            session.log.execute(
                SetEventSteps(
                    "saveButton",
                    "clicked",
                    (EventStep("validate", raw=raw_validate), EventStep("save", raw=raw_save)),
                )
            )
        _close_leftovers()
        module = _connections(root, [])
        saved = "SELECT invoice_no FROM invoices ORDER BY id"
        before = _rows(root, saved)
        for ejected in (False, True):
            if ejected:
                plan = plan_eject(session.document, scope)
                with session.log.transaction("Eject to code"):
                    for command in plan.commands:
                        session.log.execute(command)
                host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
                assert "if self.validate_fields() is False:" in Path(scope.window_path or "").read_text(encoding="utf-8")
            else:
                host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
            host.ui.invoiceNoEdit.setText("X")
            host.ui.saveButton.click()
            assert _rows(root, saved) == before
            host.ui.invoiceNoEdit.setText("LONGENOUGH")
            host.ui.saveButton.click()
            assert _rows(root, saved) == [("LONGENOUGH",)]
            before = _rows(root, saved)
            host.close()
        module.close_all()
    finally:
        if module is not None:
            _restore_connections(module)
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_preview_of_an_ejected_record_formula_does_not_crash(tmp_path: Path, qapp: QApplication) -> None:
    value = (
        '    <property name="cbcsValue" stdset="0">'
        '<string notr="true">record.invoice_no</string></property>\n'
        '    <property name="cbcsEnabledWhen" stdset="0">'
        '<string notr="true">form.isDirty</string></property>\n'
    )
    ui = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QLabel", "noLabel", "", value),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    try:
        root, scope, ui_text = _project(tmp_path, ui, _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        plan = plan_eject(session.document, scope)
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        from app.features.form_builder.integration.preview_notice import _eject_note

        assert _eject_note(session.document, scope) == (
            "This form's data code is in invoice_window.py, so Try shows the layout and lists the calls instead of running them."
        )
        source = _generate(root, Path(scope.ui_path), session.text())
        generated = Path(scope.generated_path or "")
        generated.write_text(source, encoding="utf-8")
        module = _load_module(generated, "ui_preview_ejected")
        assert "noLabel" in source
        host = QDialog()
        form = _ui_class(module)()
        form.setupUi(host)
        qapp.processEvents()
        from app.qt.QtWidgets import QLabel

        label = host.findChild(QLabel, "noLabel")
        assert label is not None
        assert label.text() == ""
        assert label.isEnabled() is False
        host.close()
    finally:
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_a_root_form_event_runs_on_the_bound_and_ejected_form(tmp_path: Path) -> None:
    event = (
        '    <property name="cbcsOnBeforeSave" stdset="0"><string notr="true">'
        '[{"do": "set", "field": "invoiceNoEdit", "formula": "\\"FROMEVENT\\""}]'
        "</string></property>\n"
    )
    ui = _scenario_ui().replace(
        '<widget class="QDialog" name="Invoice">\n',
        '<widget class="QDialog" name="Invoice">\n' + event,
        1,
    )
    module = None
    try:
        root, scope, ui_text = _project(tmp_path, ui, _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        _close_leftovers()
        module = _connections(root, [])
        saved = "SELECT invoice_no FROM invoices ORDER BY id"
        for ejected in (False, True):
            if ejected:
                plan = plan_eject(session.document, scope)
                with session.log.transaction("Eject to code"):
                    for command in plan.commands:
                        session.log.execute(command)
                host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
            else:
                host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
            source = Path(scope.generated_path or "").read_text(encoding="utf-8")
            assert ".beforeSave.connect" not in source
            host.ui.invoiceNoEdit.setText("KEEP")
            assert (host.save_record() if ejected else host.ui.cbcs_save()) is True
            assert host.ui.invoiceNoEdit.text() == "FROMEVENT"
            assert _rows(root, saved) == [("FROMEVENT",)]
            host.close()
        module.close_all()
    finally:
        if module is not None:
            _restore_connections(module)
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_a_before_save_stop_refuses_the_save_bound_and_ejected(tmp_path: Path) -> None:
    event = (
        '    <property name="cbcsOnBeforeSave" stdset="0"><string notr="true">'
        '[{"do": "stop", "message": "no X", "when": "invoiceNoEdit.text == \\"X\\""}]'
        "</string></property>\n"
    )
    ui = _scenario_ui().replace(
        '<widget class="QDialog" name="Invoice">\n',
        '<widget class="QDialog" name="Invoice">\n' + event,
        1,
    )
    module = None
    try:
        root, scope, ui_text = _project(tmp_path, ui, _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        _close_leftovers()
        module = _connections(root, [])
        saved = "SELECT invoice_no FROM invoices ORDER BY id"
        kept = "INV-1"
        for ejected in (False, True):
            if ejected:
                plan = plan_eject(session.document, scope)
                with session.log.transaction("Eject to code"):
                    for command in plan.commands:
                        session.log.execute(command)
                host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
                save = host.save_record
            else:
                host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
                save = host.ui.cbcs_save
            host.ui.invoiceNoEdit.setText("X")
            assert save() is False
            assert _rows(root, saved) == [(kept,)]
            host.ui.invoiceNoEdit.setText("Y")
            assert save() is True
            assert _rows(root, saved) == [("Y",)]
            kept = "Y"
            host.close()
        module.close_all()
    finally:
        if module is not None:
            _restore_connections(module)
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def _ejected_text(tmp_path: Path, ui: str) -> str:
    _root, scope, ui_text = _project(tmp_path, ui, _prepare, "invoice.ui", _invoice_schema())
    try:
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        plan = plan_eject(session.document, scope)
        return splice_window(render_window_class(session.document, scope=scope), plan)
    finally:
        set_schema_reader(None)


def test_ejected_window_drops_hedges_it_can_decide(tmp_path: Path) -> None:
    plain = _ejected_text(tmp_path, _scenario_ui())
    assert 'getattr(self, "_lookup_missing"' not in plain
    assert 'hasattr(self.ui, "cbcs_refresh")' not in plain
    assert "self.ui.cbcs_refresh()" not in plain
    assert "self._lookup_missing" in plain
    assert plain.count("import QDialog") == 1
    ast.parse(plain)
    formula = _scenario_ui().replace(
        '<widget class="QPushButton" name="saveButton">',
        '<widget class="QPushButton" name="saveButton">\n'
        '     <property name="cbcsEnabledWhen" stdset="0"><string notr="true">form.isDirty</string></property>',
        1,
    )
    decided = _ejected_text(tmp_path / "formula", formula)
    assert 'hasattr(self.ui, "cbcs_refresh")' not in decided
    assert "self.ui.cbcs_refresh()" in decided
    ast.parse(decided)


def test_state_collisions_include_updates_annotations_and_tuples(tmp_path: Path) -> None:
    from app.features.form_builder.engine.codegen.eject import window_objections

    try:
        _root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        plan = plan_eject(session.document, scope, _WINDOW)
        bodies = (
            "self._record += 1",
            "self._record: dict = {}",
            "self._record, self._ready = {}, False",
        )
        for body in bodies:
            window = _WINDOW.replace(
                "        self.ui.setupUi(self)\n",
                "        self.ui.setupUi(self)\n        %s\n" % body,
            )
            with pytest.raises(ValueError) as raised:
                window_objections(window, plan)
            assert "self._record" in str(raised.value)
        external = _WINDOW.replace("class InvoiceWindow(QDialog):", "class InvoiceWindow(Base):")
        notes = window_objections(external, plan)
        assert any("saved values" in note and "Base" in note for note in notes)
    finally:
        set_schema_reader(None)


def test_a_list_opens_the_selected_record_and_asks_before_leaving(tmp_path: Path) -> None:
    root, scope, ui_text = _project(tmp_path, _xml(_source(10), _widgets()), _prepare_list, "customers.ui", None)
    forms = root / "forms"
    (forms / "__init__.py").write_text("", encoding="utf-8")
    (forms / "customer_window.py").write_text(
        "class _Signal:\n"
        "    def connect(self, fn):\n"
        "        return None\n\n"
        "class CustomerWindow(object):\n"
        "    loaded = []\n"
        "    started = []\n"
        "    asked = []\n"
        "    opened = []\n"
        "    visible = False\n"
        "    allow = True\n"
        "    def __init__(self, parent=None):\n"
        "        self.ui = self\n"
        "        self.finished = _Signal()\n"
        "    def load_record(self, key):\n"
        "        CustomerWindow.loaded.append(key)\n"
        "    def new_record(self):\n"
        "        CustomerWindow.started.append(True)\n"
        "    def confirm_leave(self):\n"
        "        CustomerWindow.asked.append(True)\n"
        "        return CustomerWindow.allow\n"
        "    def cbcs_open(self, key):\n"
        "        CustomerWindow.opened.append(key)\n"
        "    def isVisible(self):\n"
        "        return CustomerWindow.visible\n"
        "    def exec(self):\n"
        "        return 0\n"
        "    def show(self):\n"
        "        return None\n"
        "    def raise_(self):\n"
        "        return None\n"
        "    def activateWindow(self):\n"
        "        return None\n"
        "    def setWindowFlag(self, flag):\n"
        "        return None\n",
        encoding="utf-8",
    )
    inserted = str(root)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    module = None
    try:
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _close_leftovers()
        module = _connections(root, [])
        host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
        import forms.customer_window as window_mod

        host.ui.customersView.selectRow(1)
        host.ui.cbcs_open_record("selected")
        assert window_mod.CustomerWindow.loaded
        assert window_mod.CustomerWindow.opened == []
        first = window_mod.CustomerWindow.loaded[-1]
        host.ui.customersView.selectRow(0)
        host.ui.cbcs_open_record("selected")
        assert window_mod.CustomerWindow.loaded[-1] != first
        host.ui.cbcs_open_record("new")
        assert window_mod.CustomerWindow.started == [True]
        window_mod.CustomerWindow.visible = True
        window_mod.CustomerWindow.allow = False
        loaded = list(window_mod.CustomerWindow.loaded)
        host.ui.cbcs_open_record("selected")
        assert window_mod.CustomerWindow.asked
        assert window_mod.CustomerWindow.loaded == loaded
        host.close()
        module.close_all()
    finally:
        if module is not None:
            _restore_connections(module)
        _drop_forms(root)


def test_eject_refuses_a_dirty_window_before_the_dialog(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.form_builder.integration.code_bridge import CodeBridge, ShellPort
    from app.features.form_builder.qtside.data_panel.eject_cmd import plan_for
    from app.qt.QtWidgets import QWidget

    editor = None
    shell = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        window = render_window_class(read_ui(ui_text, allocator=IdAllocator()).document, scope=scope)
        path = str(scope.window_path)
        Path(path).write_text(window, encoding="utf-8")
        editor = CodeEditorWidget()
        editor.setPlainText(window + "\n# unsaved\n")
        shell = QWidget()
        shell.session = session
        shell._workspace_controller = type(
            "C",
            (),
            {"widget_for_path": lambda _self, asked: editor if os.path.abspath(asked) == os.path.abspath(path) else None},
        )()
        shell.code_bridge = CodeBridge(str(root), ShellPort(shell))
        sentence = plan_for(shell)
        assert sentence == "Save or discard your changes to invoice_window.py first."
        assert Path(path).read_text(encoding="utf-8") == window
    finally:
        if editor is not None:
            editor.close()
            editor.deleteLater()
        if shell is not None:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)


def _leading_underscore_locals(source: str) -> List[str]:
    import keyword

    tree = ast.parse(source)
    defined = {
        item.name
        for item in ast.walk(tree)
        if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    found: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        used = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        for item in ast.walk(node):
            if not isinstance(item, ast.Name):
                continue
            name = item.id
            if name in defined or not name.startswith("_") or name.startswith("__") or name.startswith("_cbcs"):
                continue
            plain = name[1:]
            if plain in used or not plain.isidentifier() or keyword.iskeyword(plain):
                continue
            if name not in found:
                found.append(name)
    return found


def _ready(host: Any) -> EjectPlan:
    from app.features.form_builder.qtside.data_panel.eject_cmd import plan_for

    plan = plan_for(host)
    assert isinstance(plan, EjectPlan)
    return plan


def _shell_for(root: Path, session: Any, scope: Any, editor: Any = None, path: str = "") -> Any:
    from app.features.form_builder.integration.code_bridge import CodeBridge, ShellPort
    from app.qt.QtWidgets import QWidget

    shell = QWidget()
    shell.session = session
    shell._workspace_controller = type(
        "C",
        (),
        {
            "widget_for_path": lambda _self, asked: editor
            if editor is not None and os.path.abspath(asked) == os.path.abspath(path)
            else None
        },
    )()
    shell.code_bridge = CodeBridge(str(root), ShellPort(shell))
    return shell


def test_eject_writes_the_generated_module_and_undo_restores_it(tmp_path: Path, qapp: QApplication) -> None:
    import importlib

    module = None
    shell = None
    host = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        ui_text = session.text()
        Path(scope.ui_path).write_text(ui_text, encoding="utf-8")
        document = read_ui(ui_text, allocator=IdAllocator()).document
        stale = generate_form_module(document, scope=scope, source_bytes=ui_text.encode("utf-8")).text or ""
        generated = Path(scope.generated_path or "")
        generated.write_text(stale, encoding="utf-8")
        Path(scope.window_path or "").write_text(render_window_class(document, scope=scope), encoding="utf-8")
        (root / "forms" / "__init__.py").write_text("", encoding="utf-8")
        trio = (Path(scope.ui_path), Path(scope.window_path or ""), generated)
        before = tuple(path.read_bytes() for path in trio)
        shell = _shell_for(root, session, scope)
        from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for

        assert commit_eject(shell, _ready(shell)) == ""
        fresh = generated.read_text(encoding="utf-8")
        assert fresh != stale
        after = tuple(path.read_bytes() for path in trio)
        sql: List[str] = []
        _close_leftovers()
        module = _connections(root, sql)
        sys.modules["cbcs_connections"] = module
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        for name in ("forms", "forms.ui_invoice", "forms.invoice_window"):
            sys.modules.pop(name, None)
        window_mod = importlib.import_module("forms.invoice_window")
        _mark_run(window_mod, module)
        _install_boxes(window_mod, [], None, lambda _text: "Close", lambda: ("INV-1", True))
        ui_mod = sys.modules.get("forms.ui_invoice")
        if ui_mod is not None:
            _install_boxes(ui_mod, [], None, lambda _text: "Close", lambda: ("INV-1", True))
        window_cls = next(
            value for name, value in vars(window_mod).items() if isinstance(value, type) and name.endswith("Window")
        )
        ran: List[object] = []
        original = window_cls.save_record

        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            ran.append(self)
            return original(self, *args, **kwargs)

        window_cls.save_record = wrapped  # type: ignore[method-assign]
        host = window_cls()
        opened = [item for item in sql if item.lstrip().upper().startswith("SELECT")]
        assert opened
        assert len(opened) == len(set(opened))
        start = len(sql)
        host.ui.invoiceNoEdit.setText("CHANGED")
        host.ui.saveButton.click()
        qapp.processEvents()
        writes = [item for item in sql[start:] if item.lstrip().upper().startswith(("UPDATE", "INSERT"))]
        assert writes
        assert len(writes) == len(set(writes))
        assert ran == [host]
        host.close()
        assert session.log.undo() is True
        assert tuple(path.read_bytes() for path in trio) == before
        assert ejected_method(session.document) is None
        assert session.log.redo() is True
        assert tuple(path.read_bytes() for path in trio) == after
    finally:
        if host is not None:
            host.close()
        if module is not None:
            _restore_connections(module)
        if shell is not None:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)
        _drop_forms(tmp_path / "proj")


def test_a_dirty_form_is_saved_before_eject_and_undo_keeps_the_edit(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.features.form_builder.engine.commands.catalog import SetProperty
    from app.features.form_builder.engine.ui4.values import StringValue
    from app.features.form_builder.integration.content_source import FormContentSource
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for

    shell = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        opened = session.text()
        Path(scope.ui_path).write_text(opened, encoding="utf-8")
        Path(scope.window_path or "").write_text(
            render_window_class(read_ui(opened, allocator=IdAllocator()).document, scope=scope),
            encoding="utf-8",
        )
        source = FormContentSource(session.log, opened, scope=scope)
        node = next(item for item in session.document.iter_widgets() if item.object_name == "invoiceNoEdit")
        session.log.execute(SetProperty(node.id, "toolTip", StringValue("kept-edit")))
        shell = _shell_for(root, session, scope)
        shell._source = source
        assert commit_eject(shell, _ready(shell)) == ""
        assert "kept-edit" in Path(scope.ui_path).read_text(encoding="utf-8")
        assert ejected_method(session.document) is not None
        assert session.log.undo() is True
        assert "kept-edit" in Path(scope.ui_path).read_text(encoding="utf-8")
        assert ejected_method(session.document) is None
    finally:
        if shell is not None:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)


def test_a_failed_eject_write_drops_the_command(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    import errno

    import app.persistence.file_unit as unit
    import app.features.form_builder.qtside.data_panel.eject_cmd as eject

    shell = None
    real_replace = os.replace
    real_temp = unit.tempfile.mkstemp
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        Path(scope.ui_path).write_text(session.text(), encoding="utf-8")
        Path(scope.window_path or "").write_text(
            render_window_class(read_ui(session.text(), allocator=IdAllocator()).document, scope=scope),
            encoding="utf-8",
        )
        shell = _shell_for(root, session, scope)
        before = (Path(scope.ui_path).read_bytes(), Path(scope.window_path or "").read_bytes())
        calls = {"n": 0}

        def bad_replace(src: str, dst: str) -> None:
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError(errno.EXDEV, "simulated")
            real_replace(src, dst)

        eject.os.replace = bad_replace
        plan = eject.plan_for(shell)
        assert isinstance(plan, EjectPlan)
        sentence = eject.commit_eject(shell, plan)
        assert sentence.startswith("Couldn't save")
        assert "Nothing was changed." in sentence
        assert Path(scope.ui_path).read_bytes() == before[0]
        assert Path(scope.window_path or "").read_bytes() == before[1]
        assert ejected_method(session.document) is None
        assert session.log.undo_label() == "Save verb"
        assert not session.log.redo_label()
        assert shell._eject_notice == sentence
        names = [path.name for path in Path(scope.ui_path).parent.iterdir() if path.name.endswith(".cbcs-tmp")]
        assert names == []
    finally:
        eject.os.replace = real_replace
        unit.tempfile.mkstemp = real_temp
        if shell is not None:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)


def test_the_unit_writer_keeps_the_atomic_write_rules(tmp_path: Path) -> None:
    import errno

    from app.persistence.file_unit import commit_files, restore_file
    import app.persistence.file_unit as unit

    target = tmp_path / "real.txt"
    target.write_bytes(b"old\n")
    os.chmod(target, 0o640)
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    assert commit_files([(str(link), b"new\n", b"old\n")]) == ""
    assert target.read_bytes() == b"new\n"
    assert link.is_symlink()
    assert target.stat().st_mode & 0o777 == 0o640
    os.chmod(target, 0o444)
    refused = commit_files([(str(target), b"nope\n", b"new\n")])
    assert refused == "Couldn't save real.txt."
    assert target.read_bytes() == b"new\n"
    os.chmod(target, 0o644)
    seen: List[str] = []
    real = unit.tempfile.mkstemp

    def record(*args: Any, **kwargs: Any) -> Any:
        handle = real(*args, **kwargs)
        seen.append(handle[1])
        return handle

    calls = {"n": 0}

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.ENOSPC, "full")
        return record(*args, **kwargs)

    other = tmp_path / "other.txt"
    other.write_bytes(b"a\n")
    unit.tempfile.mkstemp = fail_second
    try:
        sentence = commit_files([(str(target), b"x\n", b"new\n"), (str(other), b"y\n", b"a\n")])
    finally:
        unit.tempfile.mkstemp = real
    assert "Nothing was changed." in sentence
    assert target.read_bytes() == b"new\n"
    assert other.read_bytes() == b"a\n"
    assert seen
    assert all(not name.endswith(".cbcs-tmp") for name in seen)
    assert len(set(seen)) == len(seen)
    os.chmod(tmp_path, 0o555)
    try:
        honest = restore_file(str(target), b"old\n")
    finally:
        os.chmod(tmp_path, 0o755)
    assert honest == "Couldn't restore real.txt."
    assert target.read_bytes() == b"new\n"


def test_a_crlf_window_stays_crlf_open_or_closed(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for

    editors = []
    shells = []
    try:
        for opened in (True, False):
            root, scope, ui_text = _project(tmp_path / ("open" if opened else "closed"), _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
            session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
            _arm_save(session)
            Path(scope.ui_path).write_text(session.text(), encoding="utf-8")
            window = render_window_class(read_ui(session.text(), allocator=IdAllocator()).document, scope=scope)
            crlf = window.replace("\r\n", "\n").replace("\n", "\r\n")
            path = Path(scope.window_path or "")
            path.write_bytes(crlf.encode("utf-8"))
            editor = None
            if opened:
                editor = CodeEditorWidget()
                editor.setPlainText(window.replace("\r\n", "\n"))
                editors.append(editor)
            shell = _shell_for(root, session, scope, editor, str(path))
            shells.append(shell)
            assert commit_eject(shell, _ready(shell)) == ""
            raw = path.read_bytes()
            assert b"\r\n" in raw
            assert b"\n" not in raw.replace(b"\r\n", b"")
    finally:
        for editor in editors:
            editor.close()
            editor.deleteLater()
        for shell in shells:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)


def test_undo_after_a_saved_ui_edit_names_the_ui_file(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for

    shell = None
    try:
        root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        _arm_save(session)
        Path(scope.ui_path).write_text(session.text(), encoding="utf-8")
        Path(scope.window_path or "").write_text(
            render_window_class(read_ui(session.text(), allocator=IdAllocator()).document, scope=scope),
            encoding="utf-8",
        )
        shell = _shell_for(root, session, scope)
        assert commit_eject(shell, _ready(shell)) == ""
        Path(scope.ui_path).write_text(Path(scope.ui_path).read_text(encoding="utf-8") + "\n", encoding="utf-8")
        assert session.log.undo() is False
        assert shell._eject_notice.startswith("invoice.ui changed")
    finally:
        if shell is not None:
            shell.close()
            shell.deleteLater()
        set_schema_reader(None)


def test_an_except_alias_keeps_the_name_it_is_bound_to() -> None:
    from app.features.form_builder.engine.codegen.eject_rewrite import _rename_locals

    source = "def save(self):\n    try:\n        return 1\n    except Exception as _error:\n        return str(_error)\n"
    edited = _rename_locals(source)
    assert "except Exception as error:" in edited
    assert "return str(error)" in edited
    assert "_error" not in edited


def test_a_stop_without_a_message_returns_false() -> None:
    from types import SimpleNamespace

    from app.features.form_builder.engine.logic.verbs.m7 import _emit_stop

    assert _emit_stop(SimpleNamespace(message="", raw=None), None) == ("return False",)
    lines = _emit_stop(SimpleNamespace(message="no X", raw=None), None)
    assert lines[-1] == "return False"
    assert "no X" in lines[0]


def test_an_ejected_try_paints_the_note_on_the_strip(qapp: QApplication) -> None:
    from app.features.form_builder.engine.ipc.protocol import TryDataPlan, TryStart
    from app.features.form_builder.qtside.preview.child.behavior import TrySink, make_host_factory
    from app.qt.QtWidgets import QLabel

    class _Writer:
        def send(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class _Ui:
        def setupUi(self, _host: Any) -> None:
            return None

    message = TryStart(
        request_id="r",
        view_id="view-eject",
        module_name="m",
        module_source="pass\n",
        window_class_name="W",
        base_class="QDialog",
        window_values=(),
        data=TryDataPlan(),
        eject_note="PLAIN STRIP",
    )
    factory = make_host_factory(TrySink(_Writer(), "view-eject", "pass\n"), message)
    chrome = factory(_Ui, "class W(object):\n    pass\n")
    try:
        label = chrome.findChild(QLabel, "preview.dataStrip.label")
        assert label is not None
        assert label.text() == "PLAIN STRIP"
    finally:
        chrome.close()
        chrome.deleteLater()
        qapp.processEvents()


def test_emit_validate_follows_whether_the_form_is_ejected(tmp_path: Path) -> None:
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.logic.verbs.m7 import _emit_validate

    ui = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources/>
 <connections/>
</ui>
"""
    path = tmp_path / "form.ui"
    path.write_text(ui, encoding="utf-8")
    session = FormSession.open(ui, path=str(path), scope=FormScope(kind="external", ui_path=str(path)))
    bound = _emit_validate(None, type("Ctx", (), {"doc": session.document})())
    assert bound == ("if not self.cbcs_validate():", "    return")
    session.log.execute(SetLogic(session.document.root.id, "cbcsEjected", "load_record"))
    ejected = _emit_validate(None, type("Ctx", (), {"doc": session.document})())
    assert ejected == ("if self._form.validate_fields() is False:", "    return")


def _invoice_ready(tmp_path: Path) -> tuple:
    root, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
    session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
    _arm_save(session)
    ui_text = session.text()
    Path(scope.ui_path).write_text(ui_text, encoding="utf-8")
    document = read_ui(ui_text, allocator=IdAllocator()).document
    generated = Path(scope.generated_path or "")
    generated.write_text(
        generate_form_module(document, scope=scope, source_bytes=ui_text.encode("utf-8")).text or "",
        encoding="utf-8",
    )
    Path(scope.window_path or "").write_text(render_window_class(document, scope=scope), encoding="utf-8")
    (root / "forms" / "__init__.py").write_text("", encoding="utf-8")
    return root, scope, session


def test_eject_undo_and_redo_keep_file_modes(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject

    root, scope, session = _invoice_ready(tmp_path)
    ui_path = Path(scope.ui_path)
    window_path = Path(scope.window_path or "")
    generated = Path(scope.generated_path or "")
    os.chmod(ui_path, 0o644)
    os.chmod(window_path, 0o755)
    os.chmod(generated, 0o664)
    shell = _shell_for(root, session, scope)
    assert commit_eject(shell, _ready(shell)) == ""
    assert session.log.undo() is True
    assert session.log.redo() is True
    assert ui_path.stat().st_mode & 0o777 == 0o644
    assert window_path.stat().st_mode & 0o777 == 0o755
    assert generated.stat().st_mode & 0o777 == 0o664
    shell.close()
    shell.deleteLater()


def test_a_crlf_form_hashes_like_a_normal_save_and_undo_leaves_it_clean(
    tmp_path: Path, qapp: QApplication
) -> None:
    del qapp
    from app.features.form_builder.integration.content_source import FormContentSource
    from app.features.form_builder.integration.save_pipeline import finish_save
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject
    from app.persistence.file_unit import same_text

    root, scope, session = _invoice_ready(tmp_path)
    ui_path = Path(scope.ui_path)
    ui_path.write_bytes(ui_path.read_bytes().replace(b"\n", b"\r\n"))
    source = FormContentSource(session.log, session.text(), scope=scope)
    source.mark_saved(session.text())
    shell = _shell_for(root, session, scope)
    shell._source = source
    shell.form_path = lambda: scope.ui_path
    assert commit_eject(shell, _ready(shell)) == ""
    written = Path(scope.generated_path or "").read_bytes()
    finish_save(scope, session.document, session.text())
    assert Path(scope.generated_path or "").read_bytes() == written
    # Opening the ejected form marks that text saved. Undo sits behind that point.
    source.mark_saved(session.text())
    assert session.log.undo() is True
    assert source.is_dirty() is False
    disk = ui_path.read_bytes().decode("utf-8")
    assert same_text(session.text(), disk)
    assert same_text(source.current_text(), disk)
    shell.close()
    shell.deleteLater()


def test_eject_refuses_a_hand_edited_generated_file_before_the_dialog(
    tmp_path: Path, qapp: QApplication
) -> None:
    del qapp
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for

    root, scope, session = _invoice_ready(tmp_path)
    generated = Path(scope.generated_path or "")
    generated.write_text(generated.read_text(encoding="utf-8") + "\n# MY HAND EDIT\n", encoding="utf-8")
    before = generated.read_bytes()
    shell = _shell_for(root, session, scope)
    sentence = "ui_invoice.py has edits made by hand. Saving the form will replace them."
    assert plan_for(shell) == sentence
    assert commit_eject(shell, EjectPlan(
        window_filename="invoice_window.py",
        ui_filename="invoice.ui",
        first_method="",
        summary=(),
        class_block="",
        imports=(),
        commands=(),
        method_names=(),
        helper_names=(),
    )) == sentence
    assert generated.read_bytes() == before
    assert ejected_method(session.document) is None
    shell.close()
    shell.deleteLater()


def test_eject_refuses_a_dirty_generated_tab(tmp_path: Path, qapp: QApplication) -> None:
    from app.features.form_builder.qtside.data_panel.eject_cmd import plan_for
    from app.qt.QtWidgets import QPlainTextEdit

    root, scope, session = _invoice_ready(tmp_path)
    generated = Path(scope.generated_path or "")
    editor = QPlainTextEdit()
    editor.setPlainText(generated.read_text(encoding="utf-8") + "\n# MY UNSAVED HAND EDIT\n")
    shell = _shell_for(root, session, scope, editor, str(generated))
    assert plan_for(shell) == "Save or discard your changes to ui_invoice.py first."
    assert "# MY UNSAVED HAND EDIT" not in generated.read_text(encoding="utf-8")
    editor.close()
    editor.deleteLater()
    shell.close()
    shell.deleteLater()
    qapp.processEvents()
