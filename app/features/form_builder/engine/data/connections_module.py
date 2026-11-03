"""Render ``cbcs_connections.py`` from a connection set (CONTRACTS.md section 19.4).

The rendered module ships alone. It imports PySide6 and nothing from Code
Studio. ``_ask_password`` is the dialog; tests replace that name.
"""

from __future__ import annotations

import hashlib
import os

from app.features.form_builder.engine.codegen.api_types import CODEGEN_VERSION
from app.features.form_builder.engine.data.connections import (
    Connection,
    ConnectionSet,
    save_connections,
    write_connections,
)
from app.features.form_builder.engine.logic.codec import JsonObject
from app.features.form_builder.engine.project.fs import OsFileSystem

MODULE_FILENAME = "cbcs_connections.py"
SETUP_FILENAME = "connection_setup.py"
_BORDER = "#" * 80

CONNECTION_SETUP_TEMPLATE = "def on_connect(name, connection):\n    return None\n"

_HEAD = '''from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import sys
from contextlib import contextmanager

_CONNECTIONS = '''

_AFTER_TABLE = '''
_CBCS_DRIVERS = ("psycopg", "pg8000")
_CBCS_PROJECT = __SLUG__
_CBCS_PROJECT_ROOT = None

_OPEN = {}
_PASSWORDS = {}
_DEPTH = {}


class CbcsConnectionError(Exception):
    """A connection could not be opened or a password could not be asked."""


def PROJECT_ROOT():
    """``_CBCS_PROJECT_ROOT`` when the helper set it, otherwise this file's directory."""

    return _project_root()


def _project_root():
    if _CBCS_PROJECT_ROOT:
        return _CBCS_PROJECT_ROOT
    return os.path.dirname(os.path.abspath(__file__))


def _state_root():
    return os.path.join(os.path.expanduser("~"), "FreeCAD", "CBCS", "state")


def _spec(name):
    for row in _CONNECTIONS:
        if row.get("name") == name:
            return row
    raise CbcsConnectionError("This project has no connection named %s." % name)


def dialect(name):
    engine = _spec(name).get("engine")
    if engine not in ("sqlite", "postgres"):
        raise CbcsConnectionError("Connection %s has no known engine." % name)
    return engine


def set_password(name, password):
    _spec(name)
    _PASSWORDS[name] = password


def open_connection(name):
    """One connection per name for this process."""

    reason = os.environ.get("CBCS_TRY_CLOSED")
    if reason:
        raise CbcsConnectionError(reason)
    existing = _OPEN.get(name)
    if existing is not None:
        return existing
    spec = _spec(name)
    if spec.get("engine") == "sqlite":
        connection = _open_sqlite(spec)
    else:
        connection = _open_postgres(spec)
    _OPEN[name] = connection
    return connection


def close_all():
    for connection in list(_OPEN.values()):
        try:
            connection.close()
        except Exception:
            pass
    _OPEN.clear()
    _DEPTH.clear()


@contextmanager
def work(name):
    # A nested work() on the same name joins the outer connection.
    # Only the outermost block commits, or rolls back and re-raises.
    connection = open_connection(name)
    outer = _DEPTH.get(name, 0) == 0
    _DEPTH[name] = _DEPTH.get(name, 0) + 1
    try:
        yield connection
        if outer:
            connection.commit()
    except BaseException:
        if outer:
            _rollback(connection)
        raise
    finally:
        _DEPTH[name] = _DEPTH.get(name, 0) - 1
        if _DEPTH.get(name, 0) <= 0:
            _DEPTH.pop(name, None)


def text_value(value):
    """UTF-8 text for a bytes or memoryview column value."""

    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _rollback(connection):
    rollback = getattr(connection, "rollback", None)
    if rollback is not None:
        rollback()


def _open_sqlite(spec):
    relative = spec.get("file") or ""
    if not relative:
        raise CbcsConnectionError("Connection %s has no SQLite file." % spec.get("name"))
    path = _sqlite_path(relative)
    connection = sqlite3.connect(path, detect_types=0)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sqlite_path(relative):
    parts = [part for part in relative.split("/") if part]
    packaged = os.path.join(_project_root(), *parts)
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(here, "cbcs_installed.json")):
        return packaged
    dest = os.path.join(_state_root(), "apps", _CBCS_PROJECT, *parts)
    if os.path.lexists(dest):
        return dest
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copyfile(packaged, dest)
    return dest


def _open_postgres(spec):
    password = _password(spec)
    host, port = _endpoint(spec)
    database = spec.get("database") or ""
    user = spec.get("user") or ""
    errors = []
    connection = None
    for driver in _CBCS_DRIVERS:
        found, error, kind = _try_driver(driver, host, port, database, user, password)
        if found is not None:
            connection = found
            break
        # A wrong password, a down host, or a missing database is this server.
        # Trying the other driver would count a second failed login.
        if kind in ("auth", "unreachable", "no_database"):
            raise CbcsConnectionError("Can't open %s. %s" % (spec.get("name"), error))
        errors.append(error)
    if connection is None:
        raise CbcsConnectionError("Can't open %s. %s" % (spec.get("name"), "; ".join(errors)))
    try:
        _prepare(connection, spec)
    except Exception:
        try:
            connection.close()
        except Exception:
            pass
        raise
    return connection


def _try_driver(driver, host, port, database, user, password):
    try:
        if driver == "psycopg":
            import psycopg as module
        elif driver == "pg8000":
            import pg8000.dbapi as module
        else:
            module = __import__(driver)
    except Exception as exc:
        return None, "%s: %s" % (driver, _safe(exc, password)), "no_driver"
    try:
        if driver == "psycopg":
            connection = module.connect(
                host=host,
                port=port,
                dbname=database,
                user=user,
                password=password,
            )
            connection.autocommit = False
            return connection, None, None
        if driver == "pg8000":
            return module.connect(
                user=user,
                host=host,
                database=database,
                port=port,
                password=password,
            ), None, None
        opener = getattr(module, "connect", None)
        if opener is None:
            return None, "%s: no connect" % driver, "no_driver"
        return opener(host=host, port=port, user=user, password=password, database=database), None, None
    except Exception as exc:
        return None, "%s: %s" % (driver, _safe(exc, password)), _failure_kind(exc)


def _failure_kind(exc):
    """Same kinds as engine.data.tester.classify_connect_error."""

    state = ""
    for attr in ("sqlstate", "pgcode"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            state = value.upper()
            break
    if not state:
        for arg in getattr(exc, "args", ()):
            if isinstance(arg, dict):
                code = arg.get("C") or arg.get("code") or ""
                if isinstance(code, str) and code:
                    state = code.upper()
                    break
    if not state:
        upper = str(exc).upper()
        for code in ("28P01", "28000", "3D000"):
            if code in upper:
                state = code
                break
    if state in ("28P01", "28000"):
        return "auth"
    if state == "3D000":
        return "no_database"
    if isinstance(exc, ImportError):
        return "no_driver"
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout, socket.gaierror)):
        return "unreachable"
    low = str(exc).lower()
    if "password authentication failed" in low or "authentication failed" in low:
        return "auth"
    if (
        "timeout" in low
        or "timed out" in low
        or "could not connect" in low
        or "connection refused" in low
        or "name or service not known" in low
        or "no route to host" in low
    ):
        return "unreachable"
    return "other"


def _prepare(connection, spec):
    _execute(connection, "SET client_encoding TO 'UTF8'")
    schema = spec.get("schema") or "public"
    if schema != "public":
        _execute(connection, "SET search_path TO %s" % _quote_ident(schema))
    setup = spec.get("setup")
    if setup:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import connection_setup

        hook = getattr(connection_setup, setup, None)
        if hook is None:
            raise CbcsConnectionError("connection_setup.py has no %s." % setup)
        hook(spec.get("name"), connection)
    connection.commit()


def _execute(connection, sql):
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _endpoint(spec):
    host = spec.get("host") or "localhost"
    port = spec.get("port") or 5432
    entry = _machine_entry(spec.get("name") or "")
    if entry.get("host"):
        host = entry["host"]
    if entry.get("port"):
        port = int(entry["port"])
    return host, int(port)


def _password(spec):
    name = spec.get("name") or ""
    if name in _PASSWORDS:
        return _PASSWORDS[name]
    policy = spec.get("password")
    if policy in (None, "none"):
        return ""
    if policy == "machine":
        stored = _machine_entry(name).get("password")
        if isinstance(stored, str):
            _PASSWORDS[name] = stored
            return stored
    answer = _ask_password(name, spec.get("user") or "", spec.get("database") or "", policy or "ask")
    password, remember = _answer(answer, policy == "machine")
    if not isinstance(password, str):
        raise CbcsConnectionError("A password is required for %s." % name)
    _PASSWORDS[name] = password
    if policy == "machine" and remember:
        _store_password(name, password)
    return password


def _answer(answer, default_remember):
    if answer is None:
        raise CbcsConnectionError("A password is required.")
    if isinstance(answer, tuple):
        password = answer[0] if answer else None
        remember = bool(answer[1]) if len(answer) > 1 else default_remember
        return password, remember
    return answer, default_remember


def _ask_password(name, user, database, policy):
    """Hidden-echo prompt. Tests replace this function. Returns ``(password, remember)`` or None."""

    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QLineEdit,
        QVBoxLayout,
    )

    if QApplication.instance() is None:
        raise CbcsConnectionError("Can't ask for a password without a running application.")
    dialog = QDialog()
    dialog.setWindowTitle("Password")
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Password for %s on %s" % (user or name, database or name)))
    field = QLineEdit(dialog)
    field.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(field)
    remember_box = None
    if policy == "machine":
        remember_box = QCheckBox("Remember on this machine", dialog)
        layout.addWidget(remember_box)
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dialog,
    )
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    layout.addWidget(box)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    remember = bool(remember_box is not None and remember_box.isChecked())
    return field.text(), remember


def _machine_file():
    return os.path.join(_state_root(), "connections", _CBCS_PROJECT + ".json")


def _read_machine_payload():
    path = _machine_file()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _machine_entry(name):
    rows = _read_machine_payload().get("connections")
    if not isinstance(rows, dict):
        return {}
    entry = rows.get(name)
    if not isinstance(entry, dict):
        return {}
    return entry


def _store_password(name, password):
    payload = _read_machine_payload()
    rows = payload.get("connections")
    if not isinstance(rows, dict):
        rows = {}
    entry = dict(rows.get(name) or {})
    entry["password"] = password
    rows[name] = entry
    path = _machine_file()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    os.chmod(directory, 0o700)
    text = json.dumps({"version": 1, "connections": rows}) + "\\n"
    tmp = os.path.join(directory, "cbcs_machine_write.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _safe(exc, password):
    lines = str(exc).splitlines()
    line = lines[0] if lines else exc.__class__.__name__
    if password:
        line = line.replace(password, "***")
    return line
'''


def render_connections_module(connection_set: ConnectionSet, *, project_slug: str) -> str:
    """Deterministic module text. The header's body hash is the hash of the bytes after the header."""

    body = _HEAD + _table_literal(connection_set) + _AFTER_TABLE.replace("__SLUG__", repr(project_slug))
    if not body.endswith("\n"):
        body += "\n"
    source = write_connections(connection_set)
    header = _header(
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )
    return header + body


def ensure_connection_setup(project_root: str) -> bool:
    """Write ``connection_setup.py`` when it is missing. An existing file is left alone."""

    path = os.path.join(project_root, SETUP_FILENAME)
    if os.path.exists(path):
        return False
    OsFileSystem().write_text(path, CONNECTION_SETUP_TEMPLATE)
    return True


def save_project_connections(project_root: str, connection_set: ConnectionSet, *, slug: str) -> None:
    """Write ``connections.json`` and regenerate ``cbcs_connections.py`` beside it."""

    save_connections(project_root, connection_set)
    text = render_connections_module(connection_set, project_slug=slug)
    OsFileSystem().write_text(os.path.join(project_root, MODULE_FILENAME), text)


def _header(source_hash: str, body_hash: str) -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        _BORDER,
        "## Generated from connections.json by ChoreBoy Code Studio. Do not edit this file:",
        "## Edit connections in Settings › Connections.",
        "## cbcs-codegen: %s" % CODEGEN_VERSION,
        "## cbcs-source-sha256: %s" % source_hash,
        "## cbcs-body-sha256: %s" % body_hash,
        _BORDER,
    ]
    return "\n".join(lines) + "\n"


def _table_literal(connection_set: ConnectionSet) -> str:
    if not connection_set.connections:
        return "()"
    lines = ["("]
    for item in connection_set.connections:
        lines.append("    %s," % _row_literal(item))
    lines.append(")")
    return "\n".join(lines)


def _row_literal(item: Connection) -> str:
    pairs = [("name", item.name), ("title", item.title), ("engine", item.engine)]
    if item.file:
        pairs.append(("file", item.file))
    if item.host:
        pairs.append(("host", item.host))
    if item.port is not None and item.port != 5432:
        pairs.append(("port", item.port))
    if item.database:
        pairs.append(("database", item.database))
    if item.user:
        pairs.append(("user", item.user))
    if item.password:
        pairs.append(("password", item.password))
    if item.schema and item.schema != "public":
        pairs.append(("schema", item.schema))
    if item.setup and item.setup != "none":
        pairs.append(("setup", item.setup))
    if item.try_show_sql_only:
        pairs.append(("tryShowSqlOnly", True))
    pairs.extend(item.unknown)
    return "{" + ", ".join("%s: %s" % (repr(key), _py(value)) for key, value in pairs) + "}"


def _py(value: object) -> str:
    if isinstance(value, JsonObject):
        body = ", ".join("%s: %s" % (repr(key), _py(item)) for key, item in value.pairs)
        return "{%s}" % body
    if isinstance(value, tuple):
        if not value:
            return "()"
        return "(" + ", ".join(_py(item) for item in value) + ",)"
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    raise TypeError("can't embed a %s" % type(value).__name__)
