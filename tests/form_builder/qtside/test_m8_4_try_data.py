"""Try with data: the user's database is unchanged (UX-TRYD-002)."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart
from app.features.form_builder.qtside.preview.child.try_connections import (
    LOCK_TIMEOUT,
    OWN_CONNECTION,
    SAVED_ROLLED_BACK,
    GENERIC_TIMEOUT,
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
        def __init__(self, state: str, text: str = "driver") -> None:
            super().__init__(text)
            self.sqlstate = state

    assert explain_database_error(Fault("55P03"), "invoice") == LOCK_TIMEOUT.format(record="invoice")
    assert explain_database_error(
        Fault("57014", "canceling statement due to statement timeout"),
        "invoice",
        try_set_timeout=True,
        elapsed=6,
    ) == STATEMENT_TIMEOUT
    assert explain_database_error(
        Fault("57014", "canceling statement due to statement timeout"),
        "invoice",
    ) == GENERIC_TIMEOUT
    assert explain_database_error(Fault("57014", "canceling statement due to lock timeout"), "invoice") is None
    assert explain_database_error(Fault("57014"), "invoice") == GENERIC_TIMEOUT
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


@pytest.mark.logic("L-try-mode-data")
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
    assert lines[0].details == ("1. 'saved-note'",)
    assert lines[1].sentence == SAVED_ROLLED_BACK


def test_broken_connections_json_writes_nothing(tmp_path: Path) -> None:
    from app.features.form_builder.engine.data.source import RecordSource, write_data
    from app.features.form_builder.engine.ui4.values import StringValue
    from app.features.form_builder.qtside.preview.try_data_plan import plan_for

    root = tmp_path / "broken"
    db = shop_with_three(root)
    before = _hash(db)
    note = sqlite3.connect(str(db)).execute("SELECT notes FROM invoices WHERE id = 2").fetchone()
    value = ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),))
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="broken"), encoding="utf-8")
    (root / "connections.json").write_text("{ broken", encoding="utf-8")

    class Entry:
        def __init__(self, text: str) -> None:
            self.value = StringValue(text)

    class Root:
        def prop(self, name: str) -> object:
            return Entry(write_data(RecordSource("shop", "invoices", "id"))) if name == "cbcsData" else None

    class Doc:
        def __init__(self) -> None:
            self.root = Root()

    plan = plan_for(Doc(), str(root))
    assert plan.specs and plan.specs[0].refused
    session = begin_try(_message("view-broken", db, "scratch", spec=plan.specs[0], project_root=str(root)))
    assert session is not None
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("cbcs_connections_broken", root / "cbcs_connections.py")
        assert spec is not None and spec.loader is not None
        real = importlib.util.module_from_spec(spec)
        cast(Any, spec.loader).exec_module(real)
        with pytest.raises(Exception) as raised:
            with real.work("shop") as connection:
                connection.cursor().execute("UPDATE invoices SET notes = 'real-write' WHERE id = 2")
    finally:
        end_all()
    assert "real-write" not in str(raised.value)
    assert _hash(db) == before
    assert sqlite3.connect(str(db)).execute("SELECT notes FROM invoices WHERE id = 2").fetchone() == note


def test_missing_sqlite_file_is_not_created(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    (root / "data").mkdir(parents=True)
    target = root / "data" / "shop.db"
    spec = TryConnectionSpec(
        name="shop",
        mode="scratch",
        title="Shop database",
        file="data/shop.db",
        engine="sqlite",
        sqlite_path=str(target),
    )
    session = begin_try(_message("view-missing", target, "scratch", spec=spec))
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        with pytest.raises(Exception):
            module.open_connection("shop")
    finally:
        end_all()
    assert not target.exists()


def test_would_run_statements_do_not_touch_the_file(tmp_path: Path) -> None:
    db = _bare(tmp_path)
    before = _hash(db)
    session = begin_try(_message("view-bypass", db, "would_run"))
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            connection.execute("UPDATE notes SET body = 'via-conn-execute' WHERE id = '1'")
            connection.cursor().executemany(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                [("9", "via-executemany")],
            )
            connection.cursor().execute("/* audit */ INSERT INTO notes (id, body) VALUES ('8', 'via-comment')")
            connection.cursor().execute("WITH x AS (UPDATE notes SET body = 'cte' WHERE id = '1' RETURNING id) SELECT * FROM x")
    finally:
        end_all()
    assert _hash(db) == before
    assert sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM notes").fetchone() == (0,)


def test_commit_statement_in_rollback_writes_nothing(tmp_path: Path) -> None:
    db = _bare(tmp_path)
    before = _hash(db)
    begin_try(_message("view-commit", db, "rollback"))
    try:
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO notes (id, body) VALUES ('1', 'commit-stmt')")
            cursor.execute("COMMIT")
            connection.commit()
    finally:
        end_all()
    assert _hash(db) == before
    assert sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM notes").fetchone() == (0,)


def test_wal_backup_leaves_the_user_file_unchanged(tmp_path: Path) -> None:
    import os
    import shutil

    folder = tmp_path / "wal"
    folder.mkdir()
    src = folder / "shop.db"
    connection = sqlite3.connect(str(src))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE t (x)")
    connection.execute("INSERT INTO t VALUES (1)")
    connection.commit()
    snap = str(src) + ".snap"
    for ext in ("", "-wal", "-shm"):
        path = str(src) + ext
        if os.path.exists(path):
            shutil.copy(path, snap + ext)
    connection.close()

    def digest(path: str) -> Optional[str]:
        if not os.path.exists(path):
            return None
        return hashlib.sha256(open(path, "rb").read()).hexdigest()

    before = (digest(snap), digest(snap + "-wal"))
    backup_sqlite(snap, str(folder / "scratch.db"))
    after = (digest(snap), digest(snap + "-wal"))
    assert before == after
    assert before[1] is not None


def test_second_rollback_save_is_not_a_conflict(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    seen: List[str] = []
    host, session = _open(root, db, "rollback", "view-twice", seen)
    try:
        ui = host.ui
        ui.notesEdit.setText("first")
        assert ui.cbcs_save() is True
        ui.notesEdit.setText("second")
        assert ui.cbcs_save() is True
        sentences = [item.sentence for item in session.notes]
    finally:
        host.close()
        end_all()
    assert sentences.count(SAVED_ROLLED_BACK) >= 2
    assert not any("conflict" in text.lower() for text in seen)
    assert _hash(db) == before


def test_would_run_next_show_reads_the_real_row(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    seen: List[str] = []
    host, _session = _open(root, db, "would_run", "view-reshow", seen)
    try:
        ui = host.ui
        key = ui._cbcs_key
        real = sqlite3.connect(str(db)).execute("SELECT notes FROM invoices WHERE id = ?", (key,)).fetchone()
        ui.notesEdit.setText("shadowed")
        assert ui.cbcs_save() is True
        ui._cbcs_show(1)
        ui._cbcs_show(0)
        shown = ui.notesEdit.text()
    finally:
        host.close()
        end_all()
    assert shown == ("" if real is None or real[0] is None else real[0])
    assert shown != "shadowed"
    assert _hash(db) == before


def test_subclass_save_is_wrapped(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    seen: List[str] = []
    host, _session = _open(root, db, "rollback", "view-sub", seen)
    try:
        parent = type(host.ui)

        class Child(parent):
            def cbcs_save(self) -> bool:
                self.child_ran = True
                return bool(super().cbcs_save())

        bind_form_class(Child, "view-sub")
        from PySide6.QtWidgets import QDialog

        class Host(QDialog):
            def __init__(self) -> None:
                super().__init__()
                self.ui = Child()
                self.ui.setupUi(self)

        child_host = Host()
        child_host.ui.notesEdit.setText("from-child")
        assert child_host.ui.cbcs_save() is True
        assert child_host.ui.child_ran is True
        child_host.hide()
    finally:
        host.close()
        end_all()
    assert _hash(db) == before


def test_try_stop_is_sent_when_try_ends() -> None:
    from app.features.form_builder.engine.ipc.protocol import TryStop
    from app.features.form_builder.integration.preview_notice import PreviewNotices

    class Pool:
        def __init__(self) -> None:
            self.sent: List[object] = []

        def request(self, message: object, _callback: object) -> str:
            self.sent.append(message)
            return "1"

    pool = Pool()
    notices = PreviewNotices(object(), object(), pool)
    notices._trying = True
    notices.close()
    assert any(isinstance(item, TryStop) for item in pool.sent)


def test_a_leading_semicolon_does_not_change_the_real_file(tmp_path: Path) -> None:
    db = tmp_path / "shop.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE pr (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO pr VALUES (1, 'orig')")
    conn.commit()
    conn.close()
    before = _hash(db)
    spec = TryConnectionSpec(
        name="shop", mode="rollback", title="Shop", engine="sqlite", sqlite_path=str(db), record_word="note", key="id",
    )
    begin_try(TryStart(
        request_id="t", view_id="v-semi", module_name="m", module_source="pass\n",
        window_class_name="W", base_class="QDialog", window_values=(),
        data=TryDataPlan(specs=(spec,)), show_form=True,
    ))
    try:
        from app.features.form_builder.qtside.preview.child.try_connections import activate

        module = __import__("cbcs_connections")
        with activate("v-semi"):
            with module.work("shop") as connection:
                cursor = connection.cursor()
                cursor.execute("UPDATE pr SET note='smuggled' WHERE id=1")
                cursor.execute("; COMMIT")
    finally:
        end_all()
    assert _hash(db) == before


def test_a_second_statement_does_not_change_the_scratch_copy(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    session = begin_try(_message("view-multi", db, "scratch", project_root=str(root)))
    assert session is not None
    try:
        from app.features.form_builder.qtside.preview.child.try_connections import activate

        module = __import__("cbcs_connections")
        with activate("view-multi"):
            with module.work("shop") as connection:
                cursor = connection.cursor()
                cursor.execute("UPDATE invoices SET notes='multi' WHERE id=1; COMMIT")
                cursor.execute("SELECT '--'; UPDATE invoices SET notes='hidden' WHERE id=1")
        scratch = sqlite3.connect(session.scratch_file("shop"))
        note = scratch.execute("SELECT notes FROM invoices WHERE id = 1").fetchone()
        scratch.close()
        sentences = [item.sentence for item in session.notes]
    finally:
        end_all()
    assert note is not None
    assert note[0] != "multi"
    assert note[0] != "hidden"
    assert any("one statement at a time" in item for item in sentences)
    assert _hash(db) == before


def test_a_read_outside_work_lets_another_connection_write(tmp_path: Path, qapp: Any) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    session = begin_try(_message("view-out", db, "scratch", project_root=str(root)))
    assert session is not None
    try:
        from app.features.form_builder.qtside.preview.child.try_connections import activate

        module = __import__("cbcs_connections")
        with activate("view-out"):
            cursor = module.open_connection("shop").cursor()
            cursor.execute("SELECT id FROM invoices")
            rows = cursor.fetchall()
        assert rows
        other = sqlite3.connect(session.scratch_file("shop"))
        other.execute("PRAGMA busy_timeout=300")
        other.execute("UPDATE invoices SET notes='from-other' WHERE id=1")
        other.commit()
        seen = other.execute("SELECT notes FROM invoices WHERE id=1").fetchone()
        other.close()
        assert not hasattr(module.open_connection("shop"), "_raw")
    finally:
        end_all()
    assert seen == ("from-other",)
    assert _hash(db) == before


def test_an_imported_record_stays_new_after_a_rolled_back_save(tmp_path: Path, qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    root, db = _project(tmp_path)
    before = _hash(db)
    forms = root / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    (forms / "__init__.py").write_text("", encoding="utf-8")
    ui_path = forms / "invoice.ui"
    text = invoice_ui()
    ui_path.write_text(text, encoding="utf-8")
    (forms / "invoice_window.py").write_text(_generate(root, ui_path, text), encoding="utf-8")
    monkeypatch.syspath_prepend(str(root))
    seen: List[str] = []
    begin_try(_message("view-list", db, "rollback", project_root=str(root)))
    try:
        import importlib

        import sys

        from app.features.form_builder.qtside.preview.child.try_connections import activate
        from PySide6.QtWidgets import QDialog

        sys.modules.pop("forms", None)
        sys.modules.pop("forms.invoice_window", None)
        with activate("view-list"):
            namespace: dict = {}
            exec("from forms.invoice_window import Ui_Invoice", namespace)  # noqa: S102
            module = importlib.import_module("forms.invoice_window")
        _install_boxes(module, seen, None, _choose, None)
        ui_cls = _ui_class(module)

        class Host(QDialog):
            def __init__(self) -> None:
                super().__init__()
                self.ui = ui_cls()
                with activate("view-list"):
                    self.ui.setupUi(self)

        host = Host()
        host.show()
        ui = host.ui
        before_keys = list(ui._cbcs_keys)
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-LIST")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-02")
        ui.notesEdit.setText("from-list")
        assert ui.cbcs_save() is True
        assert ui._cbcs_form_is_new() is True
        assert list(ui._cbcs_keys) == before_keys
        ui.notesEdit.setText("from-list-again")
        assert ui.cbcs_save() is True
        host.hide()
    finally:
        end_all()
    assert _hash(db) == before


def test_two_open_tries_follow_the_form_that_was_imported(tmp_path: Path, qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    root, db = _project(tmp_path)
    package = tmp_path / "pkg"
    forms = package / "forms"
    forms.mkdir(parents=True)
    (forms / "__init__.py").write_text("", encoding="utf-8")
    (forms / "record_window.py").write_text(
        "def which():\n    import cbcs_connections\n    return cbcs_connections.writes_stick()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(package))
    begin_try(_message("view-a", db, "rollback", project_root=str(root)))
    begin_try(_message("view-b", db, "scratch", project_root=str(root)))
    try:
        import sys

        from app.features.form_builder.qtside.preview.child.try_connections import activate

        for name in ("forms", "forms.record_window", "forms.invoice_window"):
            sys.modules.pop(name, None)
        with activate("view-a"):
            namespace: dict = {}
            exec("from forms.record_window import which", namespace)  # noqa: S102
        assert namespace["which"]() is False
    finally:
        end_all()


def test_production_attach_sends_try_stop_when_the_preview_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.ipc.protocol import TryStop
    from app.features.form_builder.integration import preview_notice
    from app.features.form_builder.integration.preview_control import PreviewControl

    sent: List[object] = []

    class Pool:
        def request(self, message: object, _callback: object) -> str:
            sent.append(message)
            return "1"

        def subscribe(self, _view: object, _callback: object) -> object:
            return lambda: None

    pool = Pool()
    monkeypatch.setattr(
        "app.features.form_builder.qtside.preview.pool.PreviewPool.shared",
        staticmethod(lambda: pool),
    )
    surface = type("Surface", (), {"_preview_listener": None})()
    notices = preview_notice.attach(surface, object())
    notices._trying = True
    PreviewControl(surface, notices).close()
    assert any(isinstance(item, TryStop) for item in sent)


def test_a_secret_ask_holds_try_stop_until_the_password_returns(tmp_path: Path, qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.ipc.protocol import ProvideSecret, TryStop, encode_frame
    from app.features.form_builder.qtside.preview.child.session import ChildSession
    from app.features.form_builder.qtside.preview.child.try_connections import CbcsConnectionError

    class Writer:
        def send(self, _message: object) -> None:
            return None

    db = _bare(tmp_path)
    begin_try(_message("view-secret", db, "rollback"))
    child = ChildSession(Writer(), qapp)  # type: ignore[arg-type]
    child.push_line(encode_frame(TryStop(request_id="stop", view_id="view-secret")))
    child.push_line(encode_frame(ProvideSecret(request_id="sec", connection="shop", secret="pw")))
    try:
        assert child._ask_secret("shop") == "pw"
        assert session_for("view-secret") is not None
        child.drain()
        assert session_for("view-secret") is None
    finally:
        end_all()

    child._secrets.clear()
    child.push_line(encode_frame(TryStop(request_id="stop", view_id="view-secret")))
    ticks = {"n": 0}

    def clock() -> float:
        ticks["n"] += 1
        return 0 if ticks["n"] < 5 else 1000

    monkeypatch.setattr("app.features.form_builder.qtside.preview.child.session.time.monotonic", clock)
    with pytest.raises(CbcsConnectionError):
        child._ask_secret("shop")


def test_a_semicolon_inside_a_comment_names_the_comment() -> None:
    from app.features.form_builder.qtside.preview.child.try_connections import COMMENT_SEMI, ONE_STATEMENT, _blocked_sentence

    spec = TryConnectionSpec(name="shop", mode="rollback", engine="sqlite")
    assert _blocked_sentence("SELECT 1 -- old; new\n", spec) == COMMENT_SEMI
    assert _blocked_sentence("SELECT 1 /* keep; this */", spec) == COMMENT_SEMI
    assert _blocked_sentence("SELECT 1; COMMIT", spec) == ONE_STATEMENT


def test_a_later_try_closes_the_connection_from_an_orphaned_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.qtside.preview.child import try_connections as tc
    from app.features.form_builder.qtside.preview.child.try_connections import (
        CbcsConnectionError,
        TrySession,
        begin_try,
        set_secret_asker,
    )

    closed: List[str] = []

    class Raw:
        def close(self) -> None:
            closed.append("closed")

        def rollback(self) -> None:
            return None

        def cursor(self) -> "Raw":
            return self

        def execute(self, *_args: object, **_kwargs: object) -> None:
            return None

    def connect(_driver: str, _spec: object, password: str) -> Raw:
        assert password == "pw"
        return Raw()

    monkeypatch.setattr(tc, "_connect_driver", connect)
    monkeypatch.setattr(tc, "_prepare_postgres", lambda _raw, _spec: None)
    spec = TryConnectionSpec(
        name="shop", mode="rollback", title="Shop", engine="postgres",
        host="127.0.0.1", database="cbcs", user="cbcs", password_policy="ask",
    )
    first = begin_try(_start_secret("view-ask", "run-a", spec))
    assert isinstance(first, TrySession)

    def ask(_name: str) -> str:
        begin_try(_start_secret("view-ask", "run-b", spec))
        return "pw"

    set_secret_asker(ask)
    try:
        with pytest.raises(CbcsConnectionError):
            first.open_connection("shop")
        assert session_for("view-ask") is not None
        assert session_for("view-ask") is not first
    finally:
        set_secret_asker(None)
        end_all()
    assert closed == ["closed"]


def _start_secret(view: str, request: str, spec: TryConnectionSpec) -> TryStart:
    return TryStart(
        request_id=request, view_id=view, module_name="m", module_source="pass\n",
        window_class_name="W", base_class="QDialog", window_values=(),
        data=TryDataPlan(specs=(spec,)), show_form=True,
    )


def test_a_held_try_stop_does_not_end_a_later_run(tmp_path: Path, qapp: Any) -> None:
    from app.features.form_builder.engine.ipc.protocol import ProvideSecret, TryStop, encode_frame
    from app.features.form_builder.qtside.preview.child.session import ChildSession

    class Writer:
        def send(self, _message: object) -> None:
            return None

    db = _bare(tmp_path)
    begin_try(_message("view-secret", db, "rollback"))
    child = ChildSession(Writer(), qapp)  # type: ignore[arg-type]
    child._try_run["view-secret"] = "run-a"
    child.push_line(encode_frame(TryStop(request_id="stop", view_id="view-secret")))
    child.push_line(encode_frame(ProvideSecret(request_id="sec", connection="shop", secret="pw")))
    try:
        assert child._ask_secret("shop") == "pw"
        child._try_run["view-secret"] = "run-b"
        child.drain()
        assert session_for("view-secret") is not None
    finally:
        end_all()


def test_a_different_timeout_does_not_say_five_seconds() -> None:
    class Fault(Exception):
        def __init__(self, state: str, text: str = "") -> None:
            super().__init__(text)
            self.sqlstate = state

    assert explain_database_error(Fault("57014", "annulation"), "invoice", try_set_timeout=True, elapsed=6) == STATEMENT_TIMEOUT
    assert explain_database_error(Fault("57014", "annulation"), "invoice", try_set_timeout=True, elapsed=0.2) == GENERIC_TIMEOUT
    assert explain_database_error(Fault("57014", "statement timeout 30s"), "invoice", try_set_timeout=True, elapsed=6) == GENERIC_TIMEOUT
    assert explain_database_error(Fault("57014", "canceling statement due to user request"), "invoice", try_set_timeout=True, elapsed=0.1) == GENERIC_TIMEOUT


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
