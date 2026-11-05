"""The schema helper host: timeouts, cancel, secrets, and the catalog cap."""

from __future__ import annotations

import os
import signal
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.engine.data.helper import catalog
from app.features.form_builder.engine.data.schema import ROW_PROBE_LIMIT, Column, Schema, Table, write_schema
from app.features.form_builder.engine.data.schema_cache import (
    install_schema_reader,
    postgres_tester,
    refresh,
    set_schema_runner,
)
from app.features.form_builder.qtside.schema_runner import (
    register_schema_runner,
    set_helper_command,
    set_helper_timeouts,
)
from app.run.process_supervisor import ProcessSupervisor

pytestmark = pytest.mark.unit

_SECRET = "s3cret-m86-valley"
_CHILD = textwrap.dedent(
    r"""
    import json
    import sys
    import time

    PREFIX = "\x1eCBFP1 "

    def send(payload):
        sys.stdout.write(PREFIX + json.dumps(payload, sort_keys=True) + "\n")
        sys.stdout.flush()

    def read():
        line = sys.stdin.readline()
        text = line.split(" ", 1)[1] if " " in line else "{}"
        return json.loads(text)

    mode = sys.argv[1]
    if mode == "sleep":
        time.sleep(60)
    elif mode == "secret":
        read()
        send({"connection": "office", "type": "need_secret", "view_id": ""})
        reply = read()
        handle = open(sys.argv[2], "w", encoding="utf-8")
        handle.write(reply.get("secret") or "")
        handle.close()
        send({
            "ok": True,
            "request_id": "1",
            "result": {
                "ok": True,
                "schema": {
                    "connection": "office",
                    "driver": "psycopg",
                    "engine": "postgres",
                    "readAt": "2026-11-02T14:02:11",
                    "server": "PostgreSQL 9.3.25",
                    "tables": [],
                    "version": 1,
                },
            },
            "type": "response",
        })
    elif mode == "bad":
        read()
        send({
            "ok": True,
            "request_id": "1",
            "result": {"ok": True, "schema": {"tables": "nope"}},
            "type": "response",
        })
    else:
        request = read()
        if request.get("type") == "schema":
            send({
                "ok": True,
                "request_id": "1",
                "result": {
                    "ok": True,
                    "schema": {
                        "connection": "office",
                        "driver": "psycopg",
                        "engine": "postgres",
                        "readAt": "2026-11-02T14:02:11",
                        "server": "PostgreSQL 9.3.25",
                        "tables": [],
                        "version": 1,
                    },
                },
                "type": "response",
            })
        else:
            send({
                "ok": True,
                "request_id": "1",
                "result": {"driver": "psycopg", "ok": True, "server": "PostgreSQL 9.3.25", "tables": 14},
                "type": "response",
            })
    """
)


class _Cursor:
    def __init__(self, owner: "_Database") -> None:
        self._owner = owner
        self._rows = []

    def execute(self, sql, params=None):
        del params
        self._owner.sql.append(sql)
        self._rows = self._owner.answer(sql)

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        return None


class _Database:
    def __init__(self, reltuples: float, count: int, detailed: bool = False) -> None:
        self.reltuples = reltuples
        self.count = count
        self.detailed = detailed
        self.sql = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def answer(self, sql: str):
        if "LIMIT" in sql:
            return [(self.count,)]
        if "reltuples" in sql:
            return [(1, "customers", self.reltuples)]
        if not self.detailed:
            return []
        if "format_type" in sql:
            return [
                ("id", "integer", True, None),
                ("email", "text", False, None),
                ("customer_id", "integer", True, None),
            ]
        if "indisprimary" in sql:
            return [("id",)]
        if "indisunique" in sql:
            return [("email",)]
        if "contype" in sql:
            return [("customer_id", "customers", "id")]
        return []


def test_reltuples_skips_the_count_and_a_cold_table_stops_at_the_cap() -> None:
    counted = _Database(4, 99)
    warm = catalog.read_postgres(counted, "office", "2026-11-02T14:02:11", "PostgreSQL 9.3.25", "psycopg", "public")
    assert warm.tables[0].rows == 4
    assert not any(("LIMIT %d" % ROW_PROBE_LIMIT) in sql for sql in counted.sql)
    cold = _Database(0, 3)
    found = catalog.read_postgres(cold, "office", "2026-11-02T14:02:11", "PostgreSQL 9.3.25", "psycopg", "public")
    assert found.tables[0].rows == 3
    assert any("LIMIT %d" % ROW_PROBE_LIMIT in sql for sql in cold.sql)
    unknown = _Database(-1, ROW_PROBE_LIMIT)
    capped = catalog.read_postgres(unknown, "office", "2026-11-02T14:02:11", "PostgreSQL 9.3.25", "psycopg", "public")
    assert capped.tables[0].rows == ROW_PROBE_LIMIT


def test_single_column_keys_and_references_come_from_the_catalog() -> None:
    database = _Database(4, 1, detailed=True)
    schema = catalog.read_postgres(database, "office", "2026-11-02T14:02:11", "PostgreSQL 9.3.25", "psycopg", "public")
    table = schema.tables[0]
    assert table.key == "id"
    columns = {column.name: column for column in table.columns}
    assert columns["email"].unique is True
    assert columns["customer_id"].references is not None
    assert columns["customer_id"].references.table == "customers"
    assert columns["customer_id"].references.column == "id"


@pytest.mark.logic("L-schema-cache")
def test_a_slow_helper_is_unreachable_and_the_tester_uses_the_host_sentence(tmp_path: Path, monkeypatch) -> None:
    script = _script(tmp_path)
    command = [sys.executable, script, "sleep"]
    pids = _spy(monkeypatch)
    set_helper_command(command)
    set_helper_timeouts(0.3, 0.3)
    register_schema_runner()
    connection = _connection()
    try:
        outcome = refresh(str(tmp_path), connection, lambda _item: "")
        assert outcome.kind == "unreachable"
        assert outcome.reason == "took too long"
        install_schema_reader(str(tmp_path))
        result = postgres_tester(connection, lambda: "")
        assert result["kind"] == "unreachable"
        assert "took too long" not in result["message"]
        assert result["message"] == (
            "Can't reach 10.1.1.9:5432. Check the address and that the database server is running."
        )
    finally:
        _restore(pids)


def test_cancel_stops_the_helper(tmp_path: Path, monkeypatch) -> None:
    script = _script(tmp_path)
    pids = _spy(monkeypatch)
    set_helper_command([sys.executable, script, "sleep"])
    set_helper_timeouts(5, 5)
    register_schema_runner()
    box = {}

    def run() -> None:
        box["outcome"] = refresh(str(tmp_path), _connection(), lambda _item: "")

    # The spy in _spy does not know this event. Arm it on the first pid.
    thread = threading.Thread(target=run)
    thread.start()
    deadline = __import__("time").monotonic() + 5
    while not pids and __import__("time").monotonic() < deadline:
        __import__("time").sleep(0.02)
    from app.features.form_builder.engine.data.schema_cache import cancel_schema_work

    cancel_schema_work()
    thread.join(5)
    try:
        assert box["outcome"].kind == "cancelled"
        assert box["outcome"].cancelled is True
        assert pids
        assert _alive(pids[-1]) is False
    finally:
        _restore(pids)


def test_a_new_refresh_cancels_the_one_in_flight(tmp_path: Path, monkeypatch) -> None:
    script = _script(tmp_path)
    pids = _spy(monkeypatch)
    set_helper_command([sys.executable, script, "sleep"])
    set_helper_timeouts(0.4, 0.4)
    register_schema_runner()
    box = {}

    def run() -> None:
        box["first"] = refresh(str(tmp_path), _connection(), lambda _item: "")

    thread = threading.Thread(target=run)
    thread.start()
    deadline = __import__("time").monotonic() + 5
    while not pids and __import__("time").monotonic() < deadline:
        __import__("time").sleep(0.02)
    try:
        second = refresh(str(tmp_path), _connection(), lambda _item: "")
        thread.join(5)
        assert box["first"].kind == "cancelled"
        assert second.kind == "unreachable"
        assert second.reason == "took too long"
    finally:
        _restore(pids)


def test_the_password_is_not_in_the_helper_command_or_environment(tmp_path: Path, monkeypatch) -> None:
    side = tmp_path / "secret.txt"
    script = _script(tmp_path)
    captured = []
    pids = []
    real = ProcessSupervisor.start

    def spy(self, command, *, cwd, env=None):
        captured.append((list(command), {} if env is None else dict(env)))
        pid = real(self, command, cwd=cwd, env=env)
        pids.append(pid)
        return pid

    monkeypatch.setattr(ProcessSupervisor, "start", spy)
    set_helper_command([sys.executable, script, "secret", str(side)])
    set_helper_timeouts(2, 2)
    register_schema_runner()
    connection = _connection()
    try:
        outcome = refresh(str(tmp_path), connection, lambda _item: _SECRET)
        assert outcome.ok
        assert side.read_text(encoding="utf-8") == _SECRET
        assert captured
        command, env = captured[0]
        assert _SECRET not in " ".join(command)
        assert all(_SECRET not in value for value in env.values())
    finally:
        _restore(pids)


def test_the_editor_does_not_import_a_postgres_driver(tmp_path: Path, monkeypatch) -> None:
    assert "psycopg" not in sys.modules
    assert "pg8000" not in sys.modules
    script = _script(tmp_path)
    pids = _spy(monkeypatch)
    set_helper_command([sys.executable, script, "ok"])
    set_helper_timeouts(2, 2)
    register_schema_runner()
    install_schema_reader(str(tmp_path))
    connection = _connection()
    try:
        outcome = refresh(str(tmp_path), connection, lambda _item: "")
        result = postgres_tester(connection, lambda: "")
        assert outcome.ok
        assert result["ok"] is True
        assert result["server"] == "PostgreSQL 9.3.25"
        assert result["tables"] == 14
        assert result["driver"] == "psycopg"
        assert "psycopg" not in sys.modules
        assert "pg8000" not in sys.modules
    finally:
        _restore(pids)


def test_a_bad_schema_payload_keeps_the_previous_file(tmp_path: Path, monkeypatch) -> None:
    previous = Schema(
        "office",
        "postgres",
        "PostgreSQL 9.3.25",
        "2026-11-02T14:02:11",
        "psycopg",
        (Table("customers", (Column("id", "integer", False),), key="id", rows=2),),
    )
    cache = tmp_path / "cbcs" / "schema" / "office.json"
    cache.parent.mkdir(parents=True)
    text = write_schema(previous)
    cache.write_text(text, encoding="utf-8", newline="\n")
    script = _script(tmp_path)
    pids = _spy(monkeypatch)
    set_helper_command([sys.executable, script, "bad"])
    set_helper_timeouts(2, 2)
    register_schema_runner()
    try:
        outcome = refresh(str(tmp_path), _connection(), lambda _item: "")
        assert outcome.ok is False
        assert outcome.kept_previous is True
        assert cache.read_text(encoding="utf-8") == text
    finally:
        _restore(pids)


def _connection() -> Connection:
    return Connection(
        "office",
        "Office",
        "postgres",
        host="10.1.1.9",
        port=5432,
        database="shop",
        user="clerk",
        password="ask",
    )


def _script(tmp_path: Path) -> str:
    path = tmp_path / "helper_child.py"
    path.write_text(_CHILD, encoding="utf-8")
    return str(path)


def _spy(monkeypatch) -> list:
    pids = []
    real = ProcessSupervisor.start

    def spy(self, command, *, cwd, env=None):
        pid = real(self, command, cwd=cwd, env=env)
        pids.append(pid)
        return pid

    monkeypatch.setattr(ProcessSupervisor, "start", spy)
    return pids


def _restore(pids: list) -> None:
    from app.features.form_builder.engine.data.schema_cache import cancel_schema_work

    cancel_schema_work()
    set_schema_runner(None)
    set_helper_command(None)
    set_helper_timeouts(10, 20)
    _reap(pids)


def _reap(pids: list) -> None:
    for pid in pids:
        if not isinstance(pid, int) or pid <= 0:
            continue
        try:
            os.kill(pid, 0)
        except OSError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
