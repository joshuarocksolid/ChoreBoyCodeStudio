"""The generated cbcs_connections module opens SQLite and asks for passwords."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import types

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, write_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.machine import MachineEntry, machine_path, save_machine
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

_SHOP = Connection("shop", "Shop", "sqlite", file="data/shop.db")


def _names(db_path):
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT id FROM customers WHERE id >= 70").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def test_render_is_byte_stable_and_the_body_hash_matches() -> None:
    value = ConnectionSet((_SHOP,))
    one = render_connections_module(value, project_slug="shop")
    two = render_connections_module(value, project_slug="shop")
    assert one == two
    source = write_connections(value)
    source_line = [line for line in one.splitlines() if line.startswith("## cbcs-source-sha256:")][0]
    body_line = [line for line in one.splitlines() if line.startswith("## cbcs-body-sha256:")][0]
    assert source_line.split(": ", 1)[1] == hashlib.sha256(source.encode("utf-8")).hexdigest()
    border = "#" * 80
    first = one.index(border)
    second = one.index(border, first + len(border))
    body = one[second + len(border) + 1 :]
    assert body_line.split(": ", 1)[1] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    compile(one, "cbcs_connections.py", "exec")
    assert "from PySide." not in one
    assert "import PySide\n" not in one
    assert "from PySide6.QtWidgets import" in one
    assert "QLineEdit.EchoMode.Password" in one
    assert "dialog.exec()" in one
    assert "setChecked" not in one


def test_work_commits_rolls_back_nests_and_enforces_foreign_keys(tmp_path, connections_module) -> None:
    root = tmp_path / "app"
    build(str(root / "data" / "shop.db"))
    module, _text = connections_module(root, ConnectionSet((_SHOP,)), "shop")
    db_path = str(root / "data" / "shop.db")
    try:
        with module.work("shop") as connection:
            connection.execute("INSERT INTO customers (id, name) VALUES (71, 'Ada')")
        assert 71 in _names(db_path)

        try:
            with module.work("shop") as connection:
                connection.execute("INSERT INTO customers (id, name) VALUES (72, 'No')")
                raise RuntimeError("stop")
        except RuntimeError:
            pass
        assert 72 not in _names(db_path)

        with module.work("shop") as connection:
            connection.execute("INSERT INTO customers (id, name) VALUES (81, 'Before')")
            try:
                with module.work("shop") as inner:
                    inner.execute("INSERT INTO customers (id, name) VALUES (82, 'Nested')")
                    raise RuntimeError("inner")
            except RuntimeError:
                pass
            connection.execute("INSERT INTO customers (id, name) VALUES (83, 'Later')")
        present = _names(db_path)
        assert {81, 82, 83} <= present

        try:
            with module.work("shop") as connection:
                with module.work("shop") as inner:
                    inner.execute("INSERT INTO customers (id, name) VALUES (84, 'Early')")
                raise RuntimeError("outer")
        except RuntimeError:
            pass
        assert 84 not in _names(db_path)

        with module.work("shop") as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO invoices (id, invoice_no, customer_id) VALUES (99, 'BAD', 999)"
                )
    finally:
        module.close_all()


def test_installed_seed_is_copied_once(tmp_path, connections_module) -> None:
    root = tmp_path / "app"
    build(str(root / "data" / "shop.db"))
    module, _text = connections_module(root, ConnectionSet((_SHOP,)), "shop")
    state = tmp_path / "state"
    module._state_root = lambda: str(state)
    (root / "cbcs_installed.json").write_text("{}\n", encoding="utf-8")
    try:
        module.open_connection("shop")
        dest = state / "apps" / "shop" / "data" / "shop.db"
        assert dest.is_file()
        module.close_all()
        connection = sqlite3.connect(str(dest))
        try:
            connection.execute("INSERT INTO customers (id, name) VALUES (55, 'kept')")
            connection.commit()
        finally:
            connection.close()
        module.open_connection("shop")
        module.close_all()
        connection = sqlite3.connect(str(dest))
        try:
            row = connection.execute("SELECT name FROM customers WHERE id = 55").fetchone()
        finally:
            connection.close()
        assert row is not None and row[0] == "kept"
    finally:
        module.close_all()


def test_password_policies_ask_machine_and_none(tmp_path, connections_module) -> None:
    root = tmp_path / "app"
    root.mkdir()
    office = Connection(
        "office",
        "Office",
        "postgres",
        host="127.0.0.1",
        database="shop",
        user="clerk",
        password="ask",
    )
    remembered = Connection(
        "remembered",
        "Remembered",
        "postgres",
        host="127.0.0.1",
        database="shop",
        user="clerk",
        password="machine",
    )
    quiet = Connection(
        "quiet",
        "Quiet",
        "postgres",
        host="127.0.0.1",
        database="shop",
        user="clerk",
        password="none",
    )
    module, _text = connections_module(root, ConnectionSet((office, remembered, quiet)), "app")
    module._CBCS_DRIVERS = ()
    asked = []

    def ask(name, user, database, policy):
        asked.append((name, user, database, policy))
        return ("hidden-secret", False)

    module._ask_password = ask
    try:
        module.open_connection("office")
    except module.CbcsConnectionError as exc:
        assert "hidden-secret" not in str(exc)
    assert asked == [("office", "clerk", "shop", "ask")]
    assert module._PASSWORDS["office"] == "hidden-secret"
    asked.clear()
    try:
        module.open_connection("office")
    except module.CbcsConnectionError as exc:
        assert "hidden-secret" not in str(exc)
    assert asked == []

    state = tmp_path / "state"
    save_machine(
        machine_path(str(state), "app"),
        (("remembered", MachineEntry(password="from-disk")),),
        project_root=str(root),
    )
    module._state_root = lambda: str(state)

    def refuse(*_args):
        raise AssertionError("the machine policy asked for a password")

    module._ask_password = refuse
    try:
        module.open_connection("remembered")
    except module.CbcsConnectionError as exc:
        assert "from-disk" not in str(exc)
    assert module._PASSWORDS["remembered"] == "from-disk"

    module._ask_password = refuse
    try:
        module.open_connection("quiet")
    except module.CbcsConnectionError:
        pass
    finally:
        module.close_all()


def test_auth_stops_at_the_first_driver_and_import_failure_tries_the_next(tmp_path, connections_module) -> None:
    root = tmp_path / "app"
    root.mkdir()
    office = Connection(
        "office",
        "Office",
        "postgres",
        host="127.0.0.1",
        database="shop",
        user="clerk",
        password="none",
    )
    module, _text = connections_module(root, ConnectionSet((office,)), "app")
    calls = []

    class _Auth(Exception):
        def __init__(self) -> None:
            super().__init__("password authentication failed for user clerk")
            self.sqlstate = "28P01"

    first = types.ModuleType("psycopg")

    def _auth_connect(**_kwargs):
        calls.append("psycopg")
        raise _Auth()

    first.connect = _auth_connect  # type: ignore[attr-defined]
    second_parent = types.ModuleType("pg8000")
    second = types.ModuleType("pg8000.dbapi")
    class _Cursor:
        def execute(self, _sql: str) -> None:
            return None

        def close(self) -> None:
            return None

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor()

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    opened_connection = _Connection()

    def _ok_connect(**_kwargs):
        calls.append("pg8000")
        return opened_connection

    second.connect = _ok_connect  # type: ignore[attr-defined]
    second_parent.dbapi = second  # type: ignore[attr-defined]
    names = ("psycopg", "pg8000", "pg8000.dbapi")
    saved = {name: sys.modules.get(name) for name in names}
    sys.modules["psycopg"] = first
    sys.modules["pg8000"] = second_parent
    sys.modules["pg8000.dbapi"] = second
    try:
        with pytest.raises(module.CbcsConnectionError) as caught:
            module.open_connection("office")
        assert calls == ["psycopg"]
        assert "pg8000" not in str(caught.value)
        calls.clear()
        sys.modules["psycopg"] = None
        opened = module.open_connection("office")
        assert opened is opened_connection
        assert calls == ["pg8000"]
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        module.close_all()
