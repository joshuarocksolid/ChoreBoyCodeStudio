"""Record navigation, save, delete, find, and the data checks (CONTRACTS.md section 19.5)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table
from app.features.form_builder.engine.data.source import RecordSource, Source, write_data
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

SAVE = "save"
DISCARD = "discard"
CANCEL = "cancel"


@pytest.mark.logic("L-form-data-source", "L-field-bindings", "L-record-navigation")
def test_invoice_story_reads_and_writes_sqlite_rows(tmp_path: Path) -> None:
    seen: List[str] = []

    def choose(text: str) -> str:
        if text.startswith("Delete this"):
            return "Delete"
        if text.startswith("Someone else"):
            return "Cancel"
        return "Close"

    with record_window(tmp_path, invoice_ui(), shop_with_three, choose=choose, finder=lambda: ("INV-3", True), seen=seen) as (host, db):
        run_invoice_story(host, db, seen)


def run_invoice_story(host: Any, db: Any, seen: Sequence[str]) -> None:
    assert host.ui.invoiceNoEdit.text() == "INV-3"
    assert host.ui.customerIdSpin.value() == 1
    assert host.ui.invoiceDateEdit.text() == "2026-03-01"
    assert host.ui._cbcs_form_position() == 1
    assert host.ui._cbcs_form_count() == 3
    assert host.ui._cbcs_form_is_new() is False
    host.ui.cbcs_next()
    assert host.ui.invoiceNoEdit.text() == "INV-2"
    assert host.ui._cbcs_form_position() == 2
    host.ui.cbcs_previous()
    assert host.ui.invoiceNoEdit.text() == "INV-3"
    host.ui.notesEdit.setText("draft")
    assert host.ui._cbcs_is_dirty() is True
    host.ui.cbcs_revert()
    assert host.ui.notesEdit.text() == ""
    assert host.ui._cbcs_is_dirty() is False
    reverted = _fetch(db, "INV-3")
    assert reverted is not None and reverted[4] == ""
    host.ui.notesEdit.setText("saved-note")
    assert host.ui.cbcs_save() is True
    saved = _fetch(db, "INV-3")
    assert saved is not None and saved[1:] == ("INV-3", 1, "2026-03-01", "saved-note")
    host.ui.cbcs_new()
    assert host.ui._cbcs_form_is_new() is True
    host.ui.invoiceNoEdit.setText("INV-NEW")
    host.ui.customerIdSpin.setValue(1)
    host.ui.invoiceDateEdit.setText("2026-04-01")
    host.ui.notesEdit.setText("fresh")
    assert host.ui.cbcs_save() is True
    created = _fetch(db, "INV-NEW")
    assert created is not None
    assert created[1:] == ("INV-NEW", 1, "2026-04-01", "fresh")
    assert host.ui.cbcs_current_key() == created[0]
    assert host.ui.cbcs_delete() is True
    assert _fetch(db, "INV-NEW") is None
    assert any(text == "Delete this invoice?" for text in seen)
    host.ui.cbcs_find()
    assert host.ui._cbcs_form_is_filtered() is True
    assert host.ui.invoiceNoEdit.text() == "INV-3"
    host.ui.cbcs_show_all()
    assert host.ui._cbcs_form_is_filtered() is False
    assert host.ui.invoiceNoEdit.text() == "INV-3"
    assert host.ui.cbcs_current_key() == saved[0]
    _mutate(db, "INV-3", "other")
    host.ui.notesEdit.setText("mine")
    assert host.ui.cbcs_save() is False
    conflicted = _fetch(db, "INV-3")
    assert conflicted is not None and conflicted[4] == "other"
    assert any(text.startswith("Someone else changed this invoice") for text in seen)
    _drop_row(db, "INV-3")
    assert host.ui.cbcs_save() is False
    assert _fetch(db, "INV-3") is None
    assert _notes_row(db, "mine") is None
    assert any("deleted by someone else" in text for text in seen)


def test_a_date_in_a_check_box_is_fb304() -> None:
    doc = _document(
        _xml(
            RecordSource("shop", "invoices", "id"),
            (("QCheckBox", "flag", "when_on", ""),),
        )
    )
    schema = _schema(
        (Column("id", "INTEGER", False), Column("when_on", "date", True)),
        "id",
    )
    found = [item for item in run_checks(doc, None, schema) if item.code == "FB304"]
    assert [item.message for item in found] == ["A date column can't be shown in a check box."]


def test_a_spin_box_may_show_customer_id() -> None:
    doc = _document(
        _xml(
            RecordSource("shop", "invoices", "id"),
            (("QSpinBox", "customerIdSpin", "customer_id", ""),),
        )
    )
    schema = _schema(
        (
            Column("id", "INTEGER", False),
            Column("customer_id", "INTEGER", False, references=Reference("customers", "id")),
        ),
        "id",
    )
    assert [item.code for item in run_checks(doc, None, schema) if item.code == "FB304"] == []


def test_uuid_and_a_short_spin_box_are_fb304() -> None:
    doc = _document(
        _xml(
            RecordSource("shop", "invoices", "id"),
            (
                ("QLineEdit", "tokenEdit", "token", ""),
                ("QDoubleSpinBox", "amountSpin", "amount", "<property name=\"decimals\"><number>2</number></property>"),
            ),
        )
    )
    schema = _schema(
        (
            Column("id", "INTEGER", False),
            Column("token", "uuid", True),
            Column("amount", "numeric(10,4)", True),
        ),
        "id",
    )
    messages = [item.message for item in run_checks(doc, None, schema) if item.code == "FB304"]
    assert "A uuid column can't be shown in a field." in messages
    assert any("spin box" in message for message in messages)


def test_a_table_without_one_key_is_fb306() -> None:
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), ()))
    missing = _schema((Column("id", "INTEGER", False),), None)
    found = [item for item in run_checks(doc, None, missing) if item.code == "FB306"]
    assert len(found) == 1
    assert "invoices" in found[0].message
    text_key = _schema((Column("code", "TEXT", False), Column("notes", "TEXT", True)), "code")
    bound = _document(_xml(RecordSource("shop", "invoices", "code"), (("QLineEdit", "notesEdit", "notes", ""),)))
    assert any(item.code == "FB306" for item in run_checks(bound, None, text_key))
    assert [item.code for item in run_checks(bound, None, None) if item.code == "FB306"] == []
    integer = _schema((Column("id", "INTEGER", False),), "id")
    assert [item.code for item in run_checks(doc, None, integer) if item.code == "FB306"] == []
    bigint = _schema((Column("id", "BIGINT", False),), "id")
    assert any(item.code == "FB306" for item in run_checks(doc, None, bigint))
    without = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (Table("invoices", (Column("id", "INTEGER", False),), key="id", without_rowid=True),),
    )
    assert any(item.code == "FB306" for item in run_checks(doc, None, without))
    typed = _document(_xml(RecordSource("shop", "invoices", "code"), (("QLineEdit", "codeEdit", "code", ""),)))
    assert [item.code for item in run_checks(typed, None, text_key) if item.code == "FB306"] == []


def test_a_quote_in_a_name_is_fb307_and_a_space_is_not() -> None:
    spaced = _document(
        _xml(RecordSource("shop", "invoice items", "id"), (("QLineEdit", "notesEdit", "bad-name", ""),))
    )
    assert [item.code for item in run_checks(spaced, None, None) if item.code == "FB307"] == []
    quoted = _document(
        _xml(RecordSource("shop", 'say"hi', "id"), (("QLineEdit", "notesEdit", "notes", ""),))
    )
    found = [item.message for item in run_checks(quoted, None, None) if item.code == "FB307"]
    assert any('say"hi' in message for message in found)


def test_two_fields_on_one_column_is_fb308() -> None:
    doc = _document(
        _xml(
            RecordSource("shop", "invoices", "id"),
            (("QLineEdit", "notesEdit", "notes", ""), ("QLineEdit", "againEdit", "notes", "")),
        )
    )
    found = [item for item in run_checks(doc, None, None) if item.code == "FB308"]
    assert len(found) == 1
    assert found[0].message == "notes is bound to both notesEdit and againEdit."


def test_a_required_column_with_no_field_is_fb319() -> None:
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QLineEdit", "invoiceNoEdit", "invoice_no", ""),)))
    schema = _schema(
        (
            Column("id", "INTEGER", False),
            Column("invoice_no", "TEXT", False),
            Column("notes", "TEXT", False),
        ),
        "id",
    )
    found = [item for item in run_checks(doc, None, schema) if item.code == "FB319"]
    assert len(found) == 1
    assert "notes" in found[0].message
    assert "id" not in found[0].message


def test_an_unknown_connection_is_fb301_and_a_quiet_hash_is_not(tmp_path: Path) -> None:
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), ()))
    other = ConnectionSet((Connection("other", "Other", "sqlite", file="data/other.db"),))
    assert any(item.code == "FB301" for item in run_checks(doc, other, None))
    assert [item.code for item in run_checks(doc, None, None) if item.code == "FB301"] == []
    original = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),))
    changed = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/other.db"),))
    (tmp_path / "cbcs_connections.py").write_text(
        render_connections_module(original, project_slug="m82"),
        encoding="utf-8",
    )
    doc.project_root = str(tmp_path)  # type: ignore[attr-defined]
    assert [item.code for item in run_checks(doc, original, None) if item.code == "FB305"] == []
    assert any(item.code == "FB305" for item in run_checks(doc, changed, None))


def invoice_ui() -> str:
    return _xml(
        RecordSource(
            "shop",
            "invoices",
            "id",
            order=(("invoice_date", "desc"), ("id", "desc")),
        ),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "customerIdSpin", "customer_id", ""),
            ("QLineEdit", "invoiceDateEdit", "invoice_date", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QPushButton", "saveButton", "", ""),
        ),
    )


def shop_with_three(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    build(str(path))
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (?, ?, ?, ?, ?, ?)",
            (
                (2, "INV-2", 1, "2026-02-01", "", "0"),
                (3, "INV-3", 1, "2026-03-01", "", "0"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


class record_window:
    """A generated record window and the shop database it saves into."""

    def __init__(
        self,
        tmp_path: Path,
        ui_text: str,
        prepare: Callable[[Path], Path],
        *,
        choose: Optional[Callable[[str], str]] = None,
        finder: Optional[Callable[[], Tuple[str, bool]]] = None,
        questions: Optional[List[str]] = None,
        seen: Optional[List[str]] = None,
        filename: str = "invoice.ui",
        connection_file: str = "data/shop.db",
        schema: Optional[Schema] = None,
        during: Optional[Callable[[], None]] = None,
    ) -> None:
        self._tmp = tmp_path
        self._ui = ui_text
        self._prepare = prepare
        self._choose = choose
        self._finder = finder
        self._questions = questions
        self._seen = seen if seen is not None else []
        self._filename = filename
        self._connection_file = connection_file
        self._schema = schema
        self._during = during
        self._restore: Optional[Callable[[], None]] = None
        self.host: Any = None
        self.db: Optional[Path] = None

    def __enter__(self) -> Tuple[Any, Path]:
        root = self._tmp / "proj"
        forms = root / "forms"
        forms.mkdir(parents=True)
        ui_path = forms / self._filename
        ui_path.write_text(self._ui, encoding="utf-8")
        db = self._prepare(root)
        value = ConnectionSet((Connection("shop", "Shop", "sqlite", file=self._connection_file),))
        save_connections(str(root), value)
        (root / "cbcs_connections.py").write_text(
            render_connections_module(value, project_slug="m82"),
            encoding="utf-8",
        )
        if self._schema is not None:
            from app.features.form_builder.engine.data.schema import write_schema
            from app.features.form_builder.engine.data.schema_cache import install_schema_reader

            folder = root / "cbcs" / "schema"
            folder.mkdir(parents=True)
            (folder / "shop.json").write_text(write_schema(self._schema), encoding="utf-8")
            install_schema_reader(str(root))
        source = _generate(root, ui_path, self._ui)
        generated = forms / ("ui_%s.py" % ui_path.stem)
        generated.write_text(source, encoding="utf-8")
        module = _load_module(generated, "ui_%s_m82" % ui_path.stem)
        _install_boxes(module, self._seen, self._questions, self._choose, self._finder, self._during)
        previous = sys.modules.get("cbcs_connections")
        connections = _load_module(root / "cbcs_connections.py", "cbcs_connections")
        sys.path.insert(0, str(root))
        from PySide6.QtWidgets import QApplication, QDialog

        app = QApplication.instance() or QApplication([])

        class Host(QDialog):
            def __init__(self) -> None:
                super().__init__()
                self.ui = _ui_class(module)()
                self.ui.setupUi(self)

        host = Host()
        host.show()
        app.processEvents()

        def restore() -> None:
            if self._schema is not None:
                from app.features.form_builder.engine.data.schema import set_schema_reader

                set_schema_reader(None)
            closer = getattr(connections, "close_all", None)
            if closer is not None:
                closer()
            if previous is None:
                sys.modules.pop("cbcs_connections", None)
            else:
                sys.modules["cbcs_connections"] = previous
            if sys.path and sys.path[0] == str(root):
                sys.path.pop(0)

        self._restore = restore
        self.host = host
        self.db = db
        return host, db

    def __exit__(self, *_exc: object) -> None:
        host = self.host
        if host is not None:
            timer = getattr(getattr(host, "ui", None), "_cbcs_list_timer", None)
            if timer is not None:
                timer.stop()
            host.hide()
            host.deleteLater()
            from app.qt import QtWidgets

            app = getattr(QtWidgets, "QApplication").instance()
            if app is not None:
                app.processEvents()
        if self._restore is not None:
            self._restore()


def _generate(root: Path, ui_path: Path, ui_text: str) -> str:
    read = read_ui(ui_text, allocator=IdAllocator())
    stem = ui_path.stem
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(ui_path.parent / ("ui_%s.py" % stem)),
        window_path=str(ui_path.parent / ("%s_window.py" % stem)),
        module_name="forms.ui_%s" % stem,
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=ui_text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    return result.text


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    execute = getattr(spec.loader, "exec_module", None)
    assert callable(execute)
    execute(module)
    return module


def _ui_class(module: Any) -> Any:
    names = [name for name in dir(module) if name.startswith("Ui_")]
    assert len(names) == 1, names
    return getattr(module, names[0])


def _install_boxes(
    module: Any,
    seen: List[str],
    questions: Optional[List[str]],
    choose: Optional[Callable[[str], str]],
    finder: Optional[Callable[[], Tuple[str, bool]]],
    during: Optional[Callable[[], None]] = None,
) -> None:
    from PySide6.QtWidgets import QMessageBox as RealBox

    pending = list(questions or [])
    answers = {
        SAVE: RealBox.StandardButton.Save,
        DISCARD: RealBox.StandardButton.Discard,
        CANCEL: RealBox.StandardButton.Cancel,
    }

    class MessageBox(RealBox):
        @staticmethod
        def question(_parent: object, _title: str, text: str, _buttons: object = None) -> object:  # type: ignore[override]
            seen.append(text)
            if not pending:
                raise AssertionError(text)
            label = pending.pop(0)
            return answers.get(label, label)

        @staticmethod
        def warning(_parent: object, _title: str, text: str) -> object:  # type: ignore[override]
            seen.append(text)
            if during is not None:
                during()
            return RealBox.StandardButton.Ok

        @staticmethod
        def information(_parent: object, _title: str, text: str) -> object:  # type: ignore[override]
            seen.append(text)
            return RealBox.StandardButton.Ok

        @staticmethod
        def critical(_parent: object, _title: str, text: str) -> object:  # type: ignore[override]
            seen.append(text)
            return RealBox.StandardButton.Ok

        def exec(self) -> int:  # type: ignore[override]  # noqa: A003 - Qt spells it exec
            seen.append(self.text())
            if during is not None:
                during()
            label = choose(self.text()) if choose is not None else None
            picked = None
            for button in self.buttons():
                if button.text() == label:
                    picked = button
                    break
            if picked is None:
                buttons = self.buttons()
                picked = buttons[-1] if buttons else None
            self._picked = picked
            return 0

        def clickedButton(self) -> object:  # type: ignore[override]
            return getattr(self, "_picked", None)

    class Input:
        @staticmethod
        def getText(_parent: object, _title: str, _label: str, *_args: object, **_kwargs: object) -> Tuple[str, bool]:
            if finder is None:
                return ("", False)
            return finder()

    module.QMessageBox = MessageBox
    module.QInputDialog = Input


def _fetch(db: Any, invoice_no: str) -> Optional[Tuple[Any, ...]]:
    method = getattr(db, "row", None)
    if callable(method):
        found = method(invoice_no)
        return found if isinstance(found, tuple) else None
    return _row(db, invoice_no)


def _mutate(db: Any, invoice_no: str, notes: str) -> None:
    method = getattr(db, "change", None)
    if callable(method):
        method(invoice_no, notes)
        return
    _change(db, invoice_no, notes)


def _drop_row(db: Any, invoice_no: str) -> None:
    method = getattr(db, "remove", None)
    if callable(method):
        method(invoice_no)
        return
    _remove(db, invoice_no)


def _notes_row(db: Any, notes: str) -> Optional[Tuple[Any, ...]]:
    method = getattr(db, "with_notes", None)
    if callable(method):
        found = method(notes)
        return found if isinstance(found, tuple) else None
    return _with_notes(db, notes)


def _row(db: Path, invoice_no: str) -> Optional[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute(
            "SELECT id, invoice_no, customer_id, invoice_date, notes FROM invoices WHERE invoice_no = ?",
            (invoice_no,),
        ).fetchone()
    finally:
        connection.close()


def _with_notes(db: Path, notes: str) -> Optional[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute("SELECT id FROM invoices WHERE notes = ?", (notes,)).fetchone()
    finally:
        connection.close()


def _change(db: Path, invoice_no: str, notes: str) -> None:
    connection = sqlite3.connect(str(db), timeout=5)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("UPDATE invoices SET notes = ? WHERE invoice_no = ?", (notes, invoice_no))
        connection.commit()
    finally:
        connection.close()


def _remove(db: Path, invoice_no: str) -> None:
    connection = sqlite3.connect(str(db), timeout=5)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM invoices WHERE invoice_no = ?", (invoice_no,))
        connection.commit()
    finally:
        connection.close()


def _schema(columns: Tuple[Column, ...], key: Optional[str]) -> Schema:
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (Table("invoices", columns, key=key),),
    )


def _document(text: str) -> Any:
    return read_ui(text, allocator=IdAllocator()).document


def _xml(source: Source, widgets: Sequence[Tuple[str, str, str, str]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Invoice</class>\n',
        ' <widget class="QDialog" name="Invoice">\n',
        '  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_data(source)),
        '  <layout class="QVBoxLayout" name="verticalLayout">\n',
    ]
    for class_name, name, column, extra in widgets:
        bind = ""
        if column:
            bind = '    <property name="cbcsBind" stdset="0"><string notr="true">%s</string></property>\n' % escape(column)
        parts.append(
            '   <item>\n    <widget class="%s" name="%s">\n%s%s    </widget>\n   </item>\n'
            % (class_name, name, bind, extra)
        )
    parts.append("  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n")
    return "".join(parts)
