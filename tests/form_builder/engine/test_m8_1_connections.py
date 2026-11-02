"""connections.json, the machine file, and connect-error kinds."""

from __future__ import annotations

import os
import stat

import pytest

from app.features.form_builder.engine.data.connections import (
    FB302,
    Connection,
    ConnectionSet,
    read_connections,
    write_connections,
)
from app.features.form_builder.engine.data.machine import (
    MachineEntry,
    load_machine,
    machine_path,
    rename_entry,
    save_machine,
)
from app.features.form_builder.engine.data.tester import classify_connect_error

pytestmark = pytest.mark.unit


def test_connections_round_trip_keeps_an_unknown_key(tmp_path) -> None:
    project = tmp_path / "shop"
    project.mkdir()
    value = ConnectionSet(
        (
            Connection(
                "shop",
                "Shop",
                "sqlite",
                file="data/shop.db",
                unknown=(("note", "keep-me"),),
            ),
            Connection(
                "office",
                "Office",
                "postgres",
                host="192.168.1.20",
                port=5433,
                database="shop",
                user="clerk",
                password="ask",
            ),
        ),
        unknown=(("extra", "yes"),),
    )
    text = write_connections(value)
    assert text == write_connections(value)
    assert text.endswith("\n")
    parsed, diagnostic = read_connections(text, project_root=str(project))
    assert diagnostic is None and parsed is not None
    assert parsed.connections[0].unknown == (("note", "keep-me"),)
    assert parsed.unknown == (("extra", "yes"),)
    assert parsed.connections[1].port == 5433
    assert write_connections(parsed) == text


def test_a_secret_key_is_fb302() -> None:
    text = '{"version": 1, "secret": "no", "connections": []}\n'
    _parsed, diagnostic = read_connections(text)
    assert diagnostic is not None
    assert diagnostic.code == FB302
    nested = (
        '{"version": 1, "connections": ['
        '{"name": "shop", "title": "Shop", "engine": "sqlite", "file": "shop.db", "pw": "no"}'
        "]}\n"
    )
    _parsed, diagnostic = read_connections(nested)
    assert diagnostic is not None and diagnostic.code == FB302


def test_machine_file_is_private_and_rename_moves_the_entry(tmp_path) -> None:
    project = tmp_path / "Shop"
    project.mkdir()
    state = tmp_path / "state"
    previous = os.umask(0)
    try:
        path = machine_path(str(state), "shop")
        save_machine(
            path,
            (("office", MachineEntry(password="s3cret", host="db.local", port=5433)),),
            project_root=str(project),
        )
    finally:
        os.umask(previous)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700
    assert not str(path).startswith(str(project))
    loaded = load_machine(path)
    assert loaded.entries[0][1].password == "s3cret"
    assert loaded.shared is False
    os.chmod(path, 0o644)
    loose = load_machine(path)
    assert loose.shared is True
    assert loose.entries[0][1].password == "s3cret"
    os.chmod(path, 0o600)
    rename_entry(path, "missing", "other", project_root=str(project))
    assert load_machine(path).entries[0][0] == "office"
    rename_entry(path, "office", "ledger", project_root=str(project))
    moved = dict(load_machine(path).entries)
    assert "office" not in moved
    assert moved["ledger"].password == "s3cret"
    assert moved["ledger"].host == "db.local"
    assert moved["ledger"].port == 5433


def test_classify_connect_error_maps_sqlstate_and_import_failures() -> None:
    class _State(Exception):
        def __init__(self, sqlstate: str) -> None:
            super().__init__("failed")
            self.sqlstate = sqlstate

    assert classify_connect_error(_State("28P01")) == "auth"
    assert classify_connect_error(_State("28000")) == "auth"
    assert classify_connect_error(_State("3D000")) == "no_database"
    assert classify_connect_error(ImportError("no driver")) == "no_driver"
    assert classify_connect_error(TimeoutError("timed out")) == "unreachable"
    assert classify_connect_error(RuntimeError("nope")) == "other"
    assert (
        classify_connect_error(
            RuntimeError(
                'connection failed: FATAL: password authentication failed for user "cbcs"'
            )
        )
        == "auth"
    )
