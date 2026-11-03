"""Try against PostgreSQL 9.3. Skipped unless CBCS_PG93_DSN is set."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.source import RecordSource
from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart
from app.features.form_builder.qtside.preview.child.try_connections import (
    SAVED_ROLLED_BACK,
    TRIGGER_WARNING,
    begin_try,
    bind_form_class,
    end_all,
)
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class, _xml

pytestmark = pytest.mark.pg93

_SKIP = "set CBCS_PG93_DSN to run PostgreSQL 9.3 tests"


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_try_session_leaves_postgres_rows_unchanged(tmp_path: Path, driver: str, qapp: Any) -> None:
    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    root = _project(tmp_path, fields)
    seen: List[str] = []
    host, session = _open(root, fields, "rollback", driver, "m84-%s" % driver, seen)
    try:
        ui = host.ui
        before_keys = list(ui._cbcs_keys)
        ui.notesEdit.setText("rolled-note")
        assert ui.cbcs_save() is True, seen
        assert ui.cbcs_delete() is True, seen
        assert list(ui._cbcs_keys) == before_keys
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-TRY")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-02")
        ui.notesEdit.setText("fresh")
        assert ui.cbcs_save() is True, seen
        assert ui._cbcs_form_is_new() is True
        assert list(ui._cbcs_keys) == before_keys
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute('UPDATE "m84_lines" SET "description" = %s WHERE "id" = %s', ("edited", 1))
        assert any(item.sentence == SAVED_ROLLED_BACK for item in session.notes)
        warnings = [item.sentence for item in session.notes if item.kind == "warning"]
        assert sum("m84_invoices_id_seq" in item for item in warnings) == 1
        assert sum(item == TRIGGER_WARNING.format(table="m84_invoices") for item in warnings) == 1
    finally:
        host.close()
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert after == before


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_a_held_row_lock_stops_at_the_lock_timeout(tmp_path: Path, driver: str, qapp: Any) -> None:
    raw, fields = _connect(driver)
    _reset(raw)
    root = _project(tmp_path, fields)
    seen: List[str] = []
    host, _session = _open(root, fields, "rollback", driver, "m84-lock-%s" % driver, seen)
    other = _connect(driver)[0]
    try:
        key = host.ui._cbcs_key
        cursor = other.cursor()
        cursor.execute("BEGIN")
        cursor.execute('SELECT id FROM "m84_invoices" WHERE id = %s FOR UPDATE', (key,))
        host.ui.notesEdit.setText("blocked")
        started = time.monotonic()
        assert host.ui.cbcs_save() is False
        elapsed = time.monotonic() - started
        assert 0.5 < elapsed < 4.5
        assert any("stopped waiting after 2 seconds" in text for text in seen)
    finally:
        try:
            other.rollback()
        except Exception:
            pass
        other.close()
        host.close()
        end_all()
        _reset(raw)
        raw.close()


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_would_run_and_a_hook_commit_write_nothing(tmp_path: Path, driver: str, qapp: Any) -> None:
    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    root = _project(tmp_path, fields)
    seen: List[str] = []
    host, session = _open(root, fields, "would_run", driver, "m84-would-%s" % driver, seen)
    try:
        host.ui.notesEdit.setText("not-stored")
        assert host.ui.cbcs_save() is True
        assert any(item.sentence.startswith("Would run:") for item in session.notes)
        module = __import__("cbcs_connections")
        # would_run does not take the hook path. A second session proves commit rolls back.
    finally:
        host.close()
        end_all()
    spec = _spec(fields, "rollback")
    message = _start("m84-hook-%s" % driver, spec)
    begin_try(message, drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        connection = module.open_connection("shop")
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO "m84_invoices" ("invoice_no", "customer_id", "invoice_date") VALUES (%s, %s, %s)',
            ("INV-HOOK", 1, "2026-05-01"),
        )
        connection.commit()
    finally:
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert after == before


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_commit_autocommit_and_would_run_leave_rows(tmp_path: Path, driver: str) -> None:
    del tmp_path
    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    from app.features.form_builder.qtside.preview.child.try_connections import set_secret_asker

    spec = _spec(fields, "rollback")
    asked: List[str] = []

    def ask(name: str) -> str:
        asked.append(name)
        return str(fields["password"])

    set_secret_asker(ask)
    begin_try(_start("m84-ctrl-%s" % driver, _with_policy(spec, "ask")), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute('UPDATE "m84_invoices" SET "notes" = %s WHERE "id" = %s', ("commit-stmt", 1))
            cursor.execute("COMMIT")
            connection.commit()
        try:
            module.open_connection("shop").set_autocommit(True)
        except Exception:
            pass
        try:
            module.open_connection("shop").autocommit = True
        except Exception:
            pass
        try:
            with module.open_connection("shop").transaction():
                module.open_connection("shop").cursor().execute(
                    'INSERT INTO "m84_invoices" ("invoice_no") VALUES (%s)',
                    ("txn",),
                )
        except Exception:
            pass
    finally:
        end_all()
        set_secret_asker(None)
    would = _spec(fields, "would_run")
    begin_try(_start("m84-cte-%s" % driver, would), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute(
                'WITH x AS (UPDATE "m84_invoices" SET "notes" = %s WHERE "id" = %s RETURNING "id") SELECT * FROM x',
                ("cte", 1),
            )
            cursor.executemany(
                'INSERT INTO "m84_invoices" ("invoice_no", "customer_id", "invoice_date") VALUES (%s, %s, %s)',
                [("many", 1, "2026-05-02")],
            )
            cursor.execute("/* c */ INSERT INTO \"m84_invoices\" (\"invoice_no\") VALUES ('block')")
            cursor.execute("-- note\nINSERT INTO \"m84_invoices\" (\"invoice_no\") VALUES ('dash')")
    finally:
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert asked == ["shop"]
    assert after == before


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_an_update_outside_work_stops_on_the_session_lock_timeout(driver: str) -> None:
    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    other = _connect(driver)[0]
    begin_try(_start("m84-out-%s" % driver, _spec(fields, "rollback")), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        held = other.cursor()
        held.execute("BEGIN")
        held.execute('SELECT id FROM "m84_invoices" WHERE id = %s FOR UPDATE', (1,))
        started = time.monotonic()
        with pytest.raises(Exception):
            opened = module.open_connection("shop")
            opened.cursor().execute("SET statement_timeout = '8s'")
            opened.cursor().execute('UPDATE "m84_invoices" SET "notes" = %s WHERE "id" = %s', ("x", 1))
        elapsed = time.monotonic() - started
    finally:
        try:
            other.rollback()
        except Exception:
            pass
        other.close()
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert after == before
    assert elapsed < 4.5


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
@pytest.mark.parametrize("mode", ["rollback", "would_run"])
def test_a_second_statement_and_a_side_effect_call_do_not_stick(driver: str, mode: str) -> None:
    from app.features.form_builder.qtside.preview.child.try_connections import activate

    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    seq_before = _sequence(raw)
    view = "side-%s-%s" % (driver, mode)
    session = begin_try(_start(view, _spec(fields, mode)), drivers=(driver,))
    assert session is not None
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        with activate(view):
            with module.work("shop") as connection:
                cursor = connection.cursor()
                cursor.execute("UPDATE m84_invoices SET notes='multi' WHERE id=1; COMMIT")
                cursor.execute("SELECT 1; UPDATE m84_invoices SET notes='multi2' WHERE id=1; COMMIT")
                cursor.execute("UPDATE m84_invoices SET notes='w1' WHERE id=1")
                cursor.execute("SELECT 1; COMMIT")
                cursor.execute("SELECT '--'; COMMIT")
                cursor.execute("SELECT setval('m84_invoices_id_seq', 500)")
                cursor.execute("SELECT set_config('statement_timeout', '0', false)")
                cursor.execute("EXPLAIN (ANALYZE) UPDATE m84_invoices SET notes='explained' WHERE id=1")
                cursor.execute("EXPLAIN ANALYSE UPDATE m84_invoices SET notes='explained' WHERE id=1")
                cursor.execute("SELECT nextval('m84_invoices_id_seq')")
                if mode == "would_run":
                    cursor.execute("SELECT pg_terminate_backend(0)")
                    cursor.execute("SELECT lo_import('/tmp/cbcs-no-such')")
                    cursor.execute("SELECT dblink_connect('host=127.0.0.1')")
            opened = module.open_connection("shop")
            assert not hasattr(opened, "_raw")
    finally:
        end_all()
        after = _fingerprint(raw)
        seq_after = _sequence(raw)
        _reset(raw)
        raw.close()
    assert after == before
    text = " ".join(item.sentence for item in session.notes)
    assert "one statement at a time" in text
    assert "setval" in text
    assert "set_config" in text
    assert "nextval" in text
    assert seq_after == seq_before
    if mode == "would_run":
        assert "pg_terminate_backend" in text


_SMUGGLE = (
    "SELECT 1 --x\r; COMMIT",
    "SELECT 1 AS a$$; COMMIT; SELECT 1 AS b$$",
    "SELECT 1 /* /* */ ' */ ; COMMIT; --'",
    "; COMMIT",
    ";COMMIT",
    "SELECT '$$'; COMMIT; SELECT '$$'",
    "SELECT E'\\''; COMMIT; SELECT 1",
    "SELECT 1 -- it's\n; COMMIT",
    'SELECT 1 AS "a;b"; COMMIT',
    "SELECT $a$ $b$ ; $b$ $a$; COMMIT",
    'SELECT "setval"(\'m84_invoices_id_seq\', 500)',
    'SELECT pg_catalog."setval"(\'m84_invoices_id_seq\', 500)',
    'EXPLAIN ANALYZE SELECT "setval"(\'m84_invoices_id_seq\', 500)',
    "SELECT * FROM bumpseq()",
    "SET standard_conforming_strings = off",
)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
@pytest.mark.parametrize("mode", ["rollback", "would_run"])
def test_smuggled_statements_leave_rows_and_the_sequence(driver: str, mode: str) -> None:
    from app.features.form_builder.qtside.preview.child.try_connections import activate

    raw, fields = _connect(driver)
    _reset(raw)
    raw.cursor().execute(
        "CREATE OR REPLACE FUNCTION bumpseq() RETURNS int AS $$ BEGIN PERFORM setval('m84_invoices_id_seq', 777); RETURN 1; END $$ LANGUAGE plpgsql"
    )
    raw.commit()
    before = _fingerprint(raw)
    seq_before = _sequence(raw)
    view = "smuggle-%s-%s" % (driver, mode)
    begin_try(_start(view, _spec(fields, mode)), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        with activate(view):
            with module.work("shop") as connection:
                cursor = connection.cursor()
                for sql in _SMUGGLE:
                    try:
                        cursor.execute(sql)
                    except Exception:
                        break
    finally:
        end_all()
        after = _fingerprint(raw)
        seq_after = _sequence(raw)
        raw.cursor().execute("DROP FUNCTION IF EXISTS bumpseq()")
        raw.commit()
        _reset(raw)
        raw.close()
    assert after == before
    assert seq_after == seq_before


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_the_server_rejects_a_second_command(driver: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.qtside.preview.child import try_connections as tc

    raw, _fields = _connect(driver)
    try:
        with pytest.raises(Exception) as direct:
            tc.send_extended(raw.cursor(), "SELECT 1; COMMIT")
        assert "multiple commands" in str(direct.value).lower()
    finally:
        raw.rollback()
        raw.close()
    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    monkeypatch.setattr(tc, "embedded_semicolon", lambda _sql: False)
    monkeypatch.setattr(tc, "has_extra_statement", lambda _sql: False)
    begin_try(_start("bypass-%s" % driver, _spec(fields, "rollback")), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        with tc.activate("bypass-%s" % driver):
            with pytest.raises(Exception) as caught:
                with module.work("shop") as connection:
                    connection.cursor().execute("UPDATE m84_invoices SET notes='x' WHERE id=1; COMMIT")
        assert "multiple commands" in str(caught.value).lower()
    finally:
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert after == before


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_set_config_cannot_disable_the_try_timeout(driver: str) -> None:
    from app.features.form_builder.qtside.preview.child.try_connections import STATEMENT_TIMEOUT, CbcsConnectionError, activate

    raw, fields = _connect(driver)
    _reset(raw)
    view = "timeout-%s" % driver
    begin_try(_start(view, _spec(fields, "rollback")), drivers=(driver,))
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        started = time.monotonic()
        with activate(view):
            with pytest.raises(CbcsConnectionError) as caught:
                with module.work("shop") as connection:
                    cursor = connection.cursor()
                    cursor.execute("SELECT set_config('statement_timeout', '0', false)")
                    cursor.execute("SELECT pg_sleep(7)")
        elapsed = time.monotonic() - started
    finally:
        end_all()
        _reset(raw)
        raw.close()
    assert STATEMENT_TIMEOUT in str(caught.value)
    assert elapsed < 9


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_a_read_outside_work_does_not_block_another_session(driver: str) -> None:
    from app.features.form_builder.qtside.preview.child.try_connections import activate

    raw, fields = _connect(driver)
    _reset(raw)
    before = _fingerprint(raw)
    view = "nolock-%s" % driver
    begin_try(_start(view, _spec(fields, "rollback")), drivers=(driver,))
    other = _connect(driver)[0]
    try:
        module = __import__("cbcs_connections")
        module.set_password("shop", fields["password"])
        with activate(view):
            cursor = module.open_connection("shop").cursor()
            cursor.execute("SELECT id FROM m84_invoices")
            assert cursor.fetchall()
        held = other.cursor()
        held.execute("SET lock_timeout = '2s'")
        held.execute("ALTER TABLE m84_invoices ADD COLUMN zz int")
        other.rollback()
    finally:
        other.close()
        end_all()
        after = _fingerprint(raw)
        _reset(raw)
        raw.close()
    assert after == before


def _sequence(raw: Any) -> int:
    cursor = raw.cursor()
    cursor.execute("SELECT last_value FROM m84_invoices_id_seq")
    value = int(cursor.fetchone()[0])
    raw.commit()
    return value


def _with_policy(spec: TryConnectionSpec, policy: str) -> TryConnectionSpec:
    from dataclasses import replace

    return replace(spec, password_policy=policy)


def _connect(driver: str) -> Tuple[Any, dict]:
    raw_dsn = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw_dsn:
        pytest.skip(_SKIP)
    fields = {}
    for part in raw_dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key] = value
    if driver == "psycopg":
        try:
            import psycopg  # type: ignore[import]
        except ImportError:
            pytest.skip("psycopg is not installed")
            return None, fields
        connection = psycopg.connect(raw_dsn)
        connection.autocommit = False
        return connection, fields
    try:
        import pg8000.dbapi as pg8000  # type: ignore[import]
    except ImportError:
        pytest.skip("pg8000 is not installed")
        return None, fields
    port = int(fields.get("port") or "5432")
    connection = pg8000.connect(
        user=fields["user"],
        password=fields["password"],
        host=fields.get("host") or "127.0.0.1",
        database=fields.get("dbname") or fields.get("database") or "cbcs",
        port=port,
    )
    return connection, fields


def _reset(raw: Any) -> None:
    cursor = raw.cursor()
    cursor.execute("DROP TABLE IF EXISTS m84_lines")
    cursor.execute("DROP TABLE IF EXISTS m84_invoices")
    cursor.execute("DROP TABLE IF EXISTS m84_customers")
    cursor.execute("DROP FUNCTION IF EXISTS m84_touch()")
    cursor.execute("CREATE TABLE m84_customers (id integer PRIMARY KEY, name text NOT NULL)")
    cursor.execute(
        """
        CREATE TABLE m84_invoices (
            id serial PRIMARY KEY,
            invoice_no text NOT NULL UNIQUE,
            customer_id integer NOT NULL REFERENCES m84_customers(id),
            invoice_date date,
            notes text,
            total numeric
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE m84_lines (
            id serial PRIMARY KEY,
            invoice_id integer NOT NULL REFERENCES m84_invoices(id),
            description text
        )
        """
    )
    cursor.execute(
        """
        CREATE FUNCTION m84_touch() RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER m84_t BEFORE INSERT OR UPDATE ON m84_invoices
        FOR EACH ROW EXECUTE PROCEDURE m84_touch()
        """
    )
    cursor.execute("INSERT INTO m84_customers (id, name) VALUES (1, 'Acme')")
    cursor.execute(
        """
        INSERT INTO m84_invoices (id, invoice_no, customer_id, invoice_date, notes, total)
        VALUES (1, 'INV-1', 1, '2026-03-01', '', 1.50)
        """
    )
    cursor.execute(
        """
        INSERT INTO m84_invoices (id, invoice_no, customer_id, invoice_date, notes, total)
        VALUES (2, 'INV-2', 1, '2026-04-01', '', 0)
        """
    )
    cursor.execute("INSERT INTO m84_lines (id, invoice_id, description) VALUES (1, 1, 'Widget')")
    cursor.execute("SELECT setval(pg_get_serial_sequence('m84_invoices', 'id'), 2)")
    raw.commit()


def _fingerprint(raw: Any) -> Tuple[int, str, int, str]:
    cursor = raw.cursor()
    cursor.execute("SELECT COUNT(*) FROM m84_invoices")
    invoices = int(cursor.fetchone()[0])
    cursor.execute("SELECT md5(COALESCE(string_agg(t::text, ',' ORDER BY id), '')) FROM m84_invoices t")
    invoice_hash = str(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM m84_lines")
    lines = int(cursor.fetchone()[0])
    cursor.execute("SELECT md5(COALESCE(string_agg(t::text, ',' ORDER BY id), '')) FROM m84_lines t")
    line_hash = str(cursor.fetchone()[0])
    raw.commit()
    return invoices, invoice_hash, lines, line_hash


def _project(tmp_path: Path, fields: dict) -> Path:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    port = int(fields.get("port") or "5432")
    value = ConnectionSet(
        (
            Connection(
                "shop",
                "Shop database",
                "postgres",
                host=fields.get("host") or "127.0.0.1",
                port=None if port == 5432 else port,
                database=fields.get("dbname") or fields.get("database") or "cbcs",
                user=fields["user"],
                password="none",
            ),
        )
    )
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m84"), encoding="utf-8")
    text = _xml(
        RecordSource("shop", "m84_invoices", "id", order=(("invoice_date", "desc"), ("id", "desc")), record_word="invoice"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "customerIdSpin", "customer_id", ""),
            ("QLineEdit", "invoiceDateEdit", "invoice_date", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
        ),
    )
    ui_path = forms / "invoice.ui"
    ui_path.write_text(text, encoding="utf-8")
    generated = _generate(root, ui_path, text)
    (forms / "ui_invoice.py").write_text(generated, encoding="utf-8")
    return root


def _open(
    root: Path,
    fields: dict,
    mode: str,
    driver: str,
    view: str,
    seen: List[str],
) -> Tuple[Any, Any]:
    module = _load_module(root / "forms" / "ui_invoice.py", "ui_m84_%s" % view.replace("-", "_"))
    _install_boxes(module, seen, None, _choose, None)
    session = begin_try(_start(view, _spec(fields, mode)), drivers=(driver,))
    assert session is not None
    imported = __import__("cbcs_connections")
    imported.set_password("shop", fields["password"])
    ui_cls = _ui_class(module)
    bind_form_class(ui_cls, view)
    from PySide6.QtWidgets import QDialog

    class Host(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = ui_cls()
            from app.features.form_builder.qtside.preview.child.try_connections import activate

            with activate(view):
                self.ui.setupUi(self)

    host = Host()
    host.show()
    return host, session


def _spec(fields: dict, mode: str) -> TryConnectionSpec:
    return TryConnectionSpec(
        name="shop",
        mode=mode,
        title="Shop database",
        engine="postgres",
        host=fields.get("host") or "127.0.0.1",
        port=int(fields.get("port") or "5432"),
        database=fields.get("dbname") or fields.get("database") or "cbcs",
        user=fields["user"],
        record_word="invoice",
        key="id",
        nextval=(("m84_invoices", "id", "m84_invoices_id_seq"),),
        triggers=("m84_invoices",),
    )


def _start(view: str, spec: TryConnectionSpec) -> TryStart:
    return TryStart(
        request_id="t",
        view_id=view,
        module_name="ui_invoice",
        module_source="pass\n",
        window_class_name="Window",
        base_class="QDialog",
        window_values=(),
        data=TryDataPlan(connections=(("shop", {"mode": spec.mode}),), specs=(spec,)),
        show_form=True,
    )


def _choose(prompt: str) -> str:
    if prompt.startswith("Delete this"):
        return "Delete"
    if prompt.startswith("Save changes"):
        return "Discard"
    return "Close"
