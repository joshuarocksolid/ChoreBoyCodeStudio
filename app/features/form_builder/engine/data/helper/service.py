"""One schema-helper request. The generated module is the only driver importer."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from typing import Dict, IO, Optional

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.helper import catalog
from app.features.form_builder.engine.data.schema import write_schema
from app.features.form_builder.engine.data.tester import classify_connect_error
from app.features.form_builder.engine.ipc.protocol import (
    CancelHelper,
    HelperProgress,
    NeedSecret,
    ProbeSelect,
    ProvideSecret,
    ReadSchema,
    Response,
    TestConnection,
    decode_line,
    encode_frame,
)

_DRIVER_ENV = "CBCS_FB_SCHEMA_DRIVER"


class HelperCancelled(Exception):
    """The host sent ``cancel`` while the child was waiting for a secret."""


def handle(message: object, requests: IO[str], frames: IO[str]) -> Optional[Response]:
    if isinstance(message, CancelHelper):
        return None
    if not isinstance(message, (TestConnection, ReadSchema, ProbeSelect)):
        return _failure("", "other", "bad request", "")
    connection = _connection(message.connection)
    secret = {"value": ""}
    directory = tempfile.mkdtemp(prefix="cbcs_schema_")
    inserted = False
    module = None
    try:
        module = _load(directory, connection, message.project_root, message.project_slug, requests, frames, secret)
        sys.path.insert(0, message.project_root)
        inserted = True
        opened = module.open_connection(connection.name)
        _send(frames, HelperProgress(request_id=message.request_id, phase="connected"))
        driver = str(getattr(module, "_chosen_driver", {}).get("name") or "")
        if isinstance(message, TestConnection):
            result = _test(opened, module, connection, driver)
        elif isinstance(message, ReadSchema):
            result = _schema(opened, connection, driver)
        else:
            result = _probe(opened, message.sql)
        return Response(request_id=message.request_id, ok=True, result=result)
    except HelperCancelled:
        raise
    except Exception as exc:
        kind = _kind(exc)
        return _failure(message.request_id, kind, _message(exc, secret["value"]), "")
    finally:
        if module is not None:
            close_all = getattr(module, "close_all", None)
            if callable(close_all):
                try:
                    close_all()
                except Exception:
                    pass
        if sys.modules.get("cbcs_connections") is module:
            del sys.modules["cbcs_connections"]
        if inserted and sys.path and sys.path[0] == message.project_root:
            sys.path.pop(0)
        shutil.rmtree(directory, ignore_errors=True)


def _load(
    directory: str,
    connection: Connection,
    project_root: str,
    project_slug: str,
    requests: IO[str],
    frames: IO[str],
    secret: Dict[str, str],
) -> object:
    text = render_connections_module(ConnectionSet((connection,)), project_slug=project_slug)
    path = os.path.join(directory, "cbcs_connections.py")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    spec = importlib.util.spec_from_file_location("cbcs_connections", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("can't load the connections module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cbcs_connections"] = module
    spec.loader.exec_module(module)
    module._CBCS_PROJECT_ROOT = project_root
    forced = os.environ.get(_DRIVER_ENV, "").strip()
    if forced:
        module._CBCS_DRIVERS = (forced,)
    chosen = {"name": ""}
    original = module._try_driver

    def wrapped(driver, host, port, database, user, password):  # type: ignore[no-untyped-def]
        found, error, kind = original(driver, host, port, database, user, password)
        if found is not None and not chosen["name"]:
            chosen["name"] = driver
        return found, error, kind

    module._try_driver = wrapped
    module._chosen_driver = chosen

    def ask_password(name, user, database, policy):  # type: ignore[no-untyped-def]
        del user, database, policy
        _send(frames, NeedSecret(view_id="", connection=name))
        line = requests.readline()
        if line.endswith("\n"):
            line = line[:-1]
        decoded = decode_line(line)
        if isinstance(decoded, CancelHelper):
            raise HelperCancelled()
        if not isinstance(decoded, ProvideSecret):
            raise module.CbcsConnectionError("A password is required for %s." % name)
        value = decoded.secret
        if not isinstance(value, str) or not value:
            raise module.CbcsConnectionError("A password is required for %s." % name)
        secret["value"] = value
        return (value, False)

    module._ask_password = ask_password
    return module


def _test(opened: object, _module: object, connection: Connection, driver: str) -> dict:
    return {
        "ok": True,
        "server": catalog.server_version(opened),
        "driver": driver,
        "tables": catalog.table_count(opened, connection.schema or "public"),
    }


def _schema(opened: object, connection: Connection, driver: str) -> dict:
    import datetime

    # The host overwrites read_at. This stamp only fills the object it parses.
    read_at = datetime.datetime.now().isoformat(timespec="seconds")
    schema = catalog.read_postgres(
        opened,
        connection.name,
        read_at,
        catalog.server_version(opened),
        driver,
        connection.schema or "public",
    )
    return {"ok": True, "schema": json.loads(write_schema(schema))}


def _probe(opened: object, sql: str) -> dict:
    columns = [{"name": name, "type": type_name} for name, type_name in catalog.probe_postgres(opened, sql)]
    return {"ok": True, "columns": columns}


def _connection(payload: object) -> Connection:
    if not isinstance(payload, dict):
        raise ValueError("connection must be an object")
    port = payload.get("port")
    return Connection(
        str(payload.get("name") or ""),
        str(payload.get("title") or ""),
        str(payload.get("engine") or ""),
        file=_text(payload.get("file")),
        host=_text(payload.get("host")),
        port=port if isinstance(port, int) and not isinstance(port, bool) else None,
        database=_text(payload.get("database")),
        user=_text(payload.get("user")),
        password=_text(payload.get("password")),
        schema=_text(payload.get("schema")),
        setup=_text(payload.get("setup")),
        try_show_sql_only=payload.get("tryShowSqlOnly") is True,
    )


def _text(value: object) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    return None


def _kind(exc: BaseException) -> str:
    kind = classify_connect_error(exc)
    text = str(exc).lower()
    if "no module named" in text and "psycopg" in text and "pg8000" in text:
        return "no_driver"
    # The generated module keeps the server sentence and drops the SQLSTATE.
    if kind == "other" and "does not exist" in text and "database" in text:
        return "no_database"
    return kind


def _message(exc: BaseException, secret: str) -> str:
    lines = str(exc).splitlines()
    line = lines[0] if lines else exc.__class__.__name__
    if secret:
        line = line.replace(secret, "***")
    return line


def _failure(request_id: str, kind: str, message: str, _detail: str) -> Response:
    return Response(
        request_id=request_id,
        ok=False,
        result={"ok": False, "kind": kind, "message": message},
    )


def _send(frames: IO[str], message: object) -> None:
    frames.write(encode_frame(message))
    frames.flush()
