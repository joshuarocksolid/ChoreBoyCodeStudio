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
from app.features.form_builder.engine.codegen.eject import ejected_method, method_line, plan_eject, splice_window, window_edit
from app.features.form_builder.engine.codegen.window_template import render_window_class
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_lookup
from app.features.form_builder.engine.ids import IdAllocator
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


def test_commit_eject_undo_redo_and_a_changed_window_refuses(tmp_path: Path) -> None:
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
        assert commit_eject(shell, plan) == ""
        assert editor.toPlainText() != window
        assert Path(path).read_text(encoding="utf-8") == window
        assert editor.document().isModified() is True
        assert session.log.undo() is True
        assert editor.toPlainText() == window
        assert session.text() == before
        assert session.log.redo() is True
        assert "def load_record(" in editor.toPlainText()
        assert ejected_method(session.document) == "load_record"
        longer = editor.toPlainText() + "\n# edited\n"
        editor.setPlainText(longer)
        assert session.log.undo() is False
        assert editor.toPlainText() == longer
        assert ejected_method(session.document) == "load_record"
        assert "changed after Eject" in shell._eject_notice
        shorter = longer[:-8]
        editor.setPlainText(shorter)
        assert session.log.undo() is False
        assert editor.toPlainText() == shorter
        assert ejected_method(session.document) == "load_record"
        assert Path(path).read_text(encoding="utf-8") == window
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
