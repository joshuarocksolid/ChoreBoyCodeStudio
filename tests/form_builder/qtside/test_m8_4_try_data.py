"""Try with data: the user's database is unchanged (UX-TRYD-002)."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart
from app.features.form_builder.qtside.preview.child.try_connections import (
    LOCK_TIMEOUT,
    OWN_CONNECTION,
    SAVED_ROLLED_BACK,
    STATEMENT_TIMEOUT,
    TRIGGER_WARNING,
    backup_sqlite,
    begin_try,
    bind_form_class,
    end_all,
    explain_database_error,
    session_for,
)
from app.features.form_builder.qtside.preview.try_log import TryEvent, fold
from tests.form_builder.engine.test_m8_2_scenario import (
    _generate,
    _install_boxes,
    _load_module,
    _ui_class,
    invoice_ui,
    shop_with_three,
)

pytestmark = pytest.mark.unit


def test_sqlstate_sentences() -> None:
    class Fault(Exception):
        def __init__(self, state: str) -> None:
            super().__init__("driver")
            self.sqlstate = state

    assert explain_database_error(Fault("55P03"), "invoice") == LOCK_TIMEOUT.format(record="invoice")
    assert explain_database_error(Fault("57014"), "invoice") == STATEMENT_TIMEOUT
    assert explain_database_error(Fault("23505"), "invoice") is None


def test_backup_keeps_a_committed_wal_row(tmp_path: Path) -> None:
    source = tmp_path / "shop.db"
    source.touch()
    held = sqlite3.connect(str(source))
    held.execute("PRAGMA journal_mode=WAL")
    held.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT)")
    held.execute("INSERT INTO notes VALUES ('k', 'from-wal')")
    held.commit()
    dest = tmp_path / "copy.db"
    backup_sqlite(str(source), str(dest))
    seen = sqlite3.connect(str(dest)).execute("SELECT body FROM notes").fetchone()
    held.close()
    assert seen == ("from-wal",)


def test_scratch_session_leaves_the_file_hash_unchanged(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    samples: List[float] = []
    for _index in range(3):
        started = time.perf_counter()
        backup_sqlite(str(db), str(tmp_path / ("sample-%d.db" % _index)))
        samples.append(time.perf_counter() - started)
    seen: List[str] = []
    host, session = _open(root, db, "scratch", "view-scratch", seen)
    try:
        ui = host.ui
        assert "scratch copy of data/shop.db" in session.strip_text()
        ui.notesEdit.setText("saved-note")
        save_samples: List[float] = []
        for _index in range(3):
            ui.notesEdit.setText("saved-note-%d" % _index)
            started = time.perf_counter()
            assert ui.cbcs_save() is True
            save_samples.append(time.perf_counter() - started)
        ui.cbcs_new()
        assert ui._cbcs_form_is_new() is True
        ui.invoiceNoEdit.setText("INV-NEW")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-01")
        ui.notesEdit.setText("fresh")
        assert ui.cbcs_save() is True
        assert ui.cbcs_delete() is True
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute(
                'UPDATE "invoice_lines" SET "description" = ? WHERE "id" = ?',
                ("edited line", 1),
            )
        scratch = sqlite3.connect(session.scratch_file("shop"))
        try:
            note = scratch.execute("SELECT notes FROM invoices WHERE invoice_no = 'INV-3'").fetchone()
            line = scratch.execute("SELECT description FROM invoice_lines WHERE id = 1").fetchone()
            created = scratch.execute("SELECT invoice_no FROM invoices WHERE invoice_no = 'INV-NEW'").fetchone()
        finally:
            scratch.close()
        assert note == ("saved-note-2",)
        assert line == ("edited line",)
        assert created is None
        assert any(item.kind == "ran" and "UPDATE" in item.sql for item in session.notes)
    finally:
        host.close()
        end_all()
    assert _hash(db) == before
    original = sqlite3.connect(str(db))
    try:
        assert original.execute("SELECT notes FROM invoices WHERE invoice_no = 'INV-3'").fetchone() == ("",)
        assert original.execute("SELECT description FROM invoice_lines WHERE id = 1").fetchone() == ("Widget",)
    finally:
        original.close()
    _write_timings(samples, save_samples)
    assert max(samples) < 2.0
    assert max(save_samples) < 2.0


def test_rollback_save_keeps_is_new_and_the_key_list(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    keys_before = _keys(db)
    seen: List[str] = []
    host, session = _open(root, db, "rollback", "view-rollback", seen)
    try:
        ui = host.ui
        before_keys = list(ui._cbcs_keys)
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-TRY")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-02")
        ui.notesEdit.setText("rolled")
        assert ui.cbcs_save() is True
        assert ui._cbcs_form_is_new() is True
        assert list(ui._cbcs_keys) == before_keys
        assert any(item.sentence == SAVED_ROLLED_BACK for item in session.notes)
        assert session.banner_text().startswith("Try: changes to Shop database are rolled back.")
    finally:
        host.close()
        end_all()
    assert _hash(db) == before
    assert _keys(db) == keys_before


def test_would_run_writes_nothing(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    seen: List[str] = []
    host, session = _open(root, db, "would_run", "view-would", seen)
    try:
        ui = host.ui
        ui.notesEdit.setText("not-stored")
        assert ui.cbcs_save() is True
        assert ui.notesEdit.text() == "not-stored"
        assert any(item.sentence.startswith("Would run:") for item in session.notes)
        assert not any(item.kind == "ran" and item.sql.upper().startswith("UPDATE") for item in session.notes)
    finally:
        host.close()
        end_all()
    assert _hash(db) == before


def test_a_hook_commit_in_rollback_mode_writes_nothing(tmp_path: Path) -> None:
    _db = _bare(tmp_path)
    message = _message("view-hook", _db, "rollback")
    session = begin_try(message)
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        connection = module.open_connection("shop")
        cursor = connection.cursor()
        cursor.execute('INSERT INTO "notes" ("body") VALUES (?)', ("nope",))
        connection.commit()
        module.close_all()
    finally:
        end_all()
    seen = sqlite3.connect(str(_db)).execute("SELECT COUNT(*) FROM notes").fetchone()
    assert seen == (0,)


def test_warnings_appear_once(tmp_path: Path) -> None:
    db = _bare(tmp_path)
    spec = TryConnectionSpec(
        name="shop",
        mode="rollback",
        engine="sqlite",
        sqlite_path=str(db),
        record_word="invoice",
        key="id",
        nextval=(("notes", "id", "notes_id_seq"),),
        triggers=("notes",),
    )
    message = _message("view-warn", db, "rollback", spec=spec)
    session = begin_try(message)
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        for _index in range(2):
            with module.work("shop") as connection:
                cursor = connection.cursor()
                cursor.execute('INSERT INTO "notes" ("body") VALUES (?)', ("row-%d" % _index,))
        warnings = [item.sentence for item in session.notes if item.kind == "warning"]
    finally:
        end_all()
    assert sum(1 for item in warnings if "notes_id_seq" in item) == 1
    assert sum(1 for item in warnings if item == TRIGGER_WARNING.format(table="notes")) == 1
    assert sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM notes").fetchone() == (0,)


def test_two_forms_do_not_share_a_scratch_file(tmp_path: Path) -> None:
    left = tmp_path / "left.db"
    right = tmp_path / "right.db"
    for path in (left, right):
        connection = sqlite3.connect(str(path))
        connection.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT)")
        connection.commit()
        connection.close()
    begin_try(_message("view-a", left, "scratch"))
    begin_try(_message("view-b", right, "scratch"))
    try:
        from app.features.form_builder.qtside.preview.child.try_connections import activate

        module = __import__("cbcs_connections")
        with activate("view-a"):
            with module.work("shop") as connection:
                connection.cursor().execute("INSERT INTO notes VALUES (?, ?)", ("a", "left"))
        with activate("view-b"):
            with module.work("shop") as connection:
                connection.cursor().execute("INSERT INTO notes VALUES (?, ?)", ("b", "right"))
        left_copy = session_for("view-a").scratch_file("shop")  # type: ignore[union-attr]
        right_copy = session_for("view-b").scratch_file("shop")  # type: ignore[union-attr]
        assert left_copy != right_copy
        assert sqlite3.connect(left_copy).execute("SELECT id FROM notes").fetchall() == [("a",)]
        assert sqlite3.connect(right_copy).execute("SELECT id FROM notes").fetchall() == [("b",)]
    finally:
        end_all()
    assert sqlite3.connect(str(left)).execute("SELECT COUNT(*) FROM notes").fetchone() == (0,)
    assert sqlite3.connect(str(right)).execute("SELECT COUNT(*) FROM notes").fetchone() == (0,)


def test_null_decimal_date_and_text_key_round_trip_on_the_scratch_copy(tmp_path: Path) -> None:
    db = tmp_path / "typed.db"
    connection = sqlite3.connect(str(db))
    connection.execute("CREATE TABLE codes (id TEXT PRIMARY KEY, amount TEXT, when_on TEXT, note TEXT)")
    connection.commit()
    connection.close()
    before = _hash(db)
    spec = TryConnectionSpec(
        name="shop",
        mode="scratch",
        engine="sqlite",
        sqlite_path=str(db),
        file="data/typed.db",
        key="id",
    )
    begin_try(_message("view-typed", db, "scratch", spec=spec))
    try:
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            connection.cursor().execute(
                "INSERT INTO codes (id, amount, when_on, note) VALUES (?, ?, ?, ?)",
                ("abc", str(Decimal("1.25")), "2026-04-02", None),
            )
        copy = sqlite3.connect(session_for("view-typed").scratch_file("shop"))  # type: ignore[union-attr]
        try:
            row = copy.execute("SELECT id, amount, when_on, note FROM codes").fetchone()
        finally:
            copy.close()
    finally:
        end_all()
    assert row == ("abc", "1.25", "2026-04-02", None)
    assert _hash(db) == before


def test_own_connection_logs_would_run_and_does_not_open_the_file(tmp_path: Path) -> None:
    db = _bare(tmp_path)
    before = _hash(db)
    spec = TryConnectionSpec(
        name="shop",
        mode="would_run",
        engine="sqlite",
        sqlite_path=str(db),
        own_hook=True,
        record_word="invoice",
    )
    session = begin_try(_message("view-own", db, "would_run", spec=spec))
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            connection.cursor().execute('INSERT INTO "notes" ("body") VALUES (?)', ("secret",))
        sentences = [item.sentence for item in session.notes]
    finally:
        end_all()
    assert sentences[0] == OWN_CONNECTION
    assert any(item.startswith("Would run:") for item in sentences)
    assert _hash(db) == before


def test_what_ran_expands_statement_values() -> None:
    lines = fold(
        (
            TryEvent(
                "sql",
                "",
                {"sentence": 'Ran: UPDATE "invoices" SET "notes" = ? … (1 value)', "values": ["saved-note"]},
            ),
            TryEvent("sql", "", {"sentence": SAVED_ROLLED_BACK, "values": []}),
        ),
        {},
        {},
    )
    assert lines[0].kind == "sql"
    assert lines[0].details == ("saved-note",)
    assert lines[1].sentence == SAVED_ROLLED_BACK


def _project(tmp_path: Path) -> Tuple[Path, Path]:
    root = tmp_path / "proj"
    db = shop_with_three(root)
    value = ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),))
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m84"), encoding="utf-8")
    return root, db


def _open(
    root: Path,
    db: Path,
    mode: str,
    view: str,
    seen: List[str],
    parent: Any = None,
) -> Tuple[Any, Any]:
    forms = root / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    ui_path = forms / "invoice.ui"
    text = invoice_ui()
    ui_path.write_text(text, encoding="utf-8")
    source = _generate(root, ui_path, text)
    generated = forms / "ui_invoice.py"
    generated.write_text(source, encoding="utf-8")
    module = _load_module(generated, "ui_invoice_%s" % view.replace("-", "_"))
    _install_boxes(module, seen, None, _choose, None)
    message = _message(view, db, mode, project_root=str(root))
    session = begin_try(message)
    assert session is not None
    ui_cls = _ui_class(module)
    bind_form_class(ui_cls, view)
    from PySide6.QtWidgets import QDialog

    from app.features.form_builder.qtside.preview.child.try_connections import activate

    if parent is not None:
        holder = QDialog()
        holder.ui = ui_cls()
        with activate(view):
            holder.ui.setupUi(parent)
        return holder, session

    class Host(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = ui_cls()
            with activate(view):
                self.ui.setupUi(self)

    host = Host()
    host.show()
    return host, session


def _message(
    view: str,
    db: Path,
    mode: str,
    *,
    spec: Optional[TryConnectionSpec] = None,
    project_root: str = "",
) -> TryStart:
    chosen = spec or TryConnectionSpec(
        name="shop",
        mode=mode,
        title="Shop database",
        file="data/shop.db",
        engine="sqlite",
        sqlite_path=str(db),
        record_word="invoice",
        key="id",
    )
    return TryStart(
        request_id="t",
        view_id=view,
        module_name="ui_invoice",
        module_source="pass\n",
        window_class_name="Window",
        base_class="QDialog",
        window_values=(),
        data=TryDataPlan(connections=(("shop", {"mode": mode}),), specs=(chosen,)),
        show_form=True,
        project_root=project_root,
    )


def _bare(tmp_path: Path) -> Path:
    path = tmp_path / "notes.db"
    connection = sqlite3.connect(str(path))
    connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    connection.commit()
    connection.close()
    return path


def _choose(prompt: str) -> str:
    if prompt.startswith("Delete this"):
        return "Delete"
    if prompt.startswith("Save changes"):
        return "Discard"
    return "Close"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _keys(path: Path) -> List[int]:
    connection = sqlite3.connect(str(path))
    try:
        return [row[0] for row in connection.execute("SELECT id FROM invoices ORDER BY id")]
    finally:
        connection.close()


def _write_timings(backups: List[float], saves: List[float]) -> None:
    folder = Path(__file__).resolve().parents[3] / "scratchpad"
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        "scratch backup samples: %s" % ", ".join("%.4fs" % item for item in backups),
        "try save samples: %s" % ", ".join("%.4fs" % item for item in saves),
    ]
    (folder / "m84_timings.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
