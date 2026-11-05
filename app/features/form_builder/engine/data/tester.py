"""The PostgreSQL test seam (CONTRACTS.md section 19.7).

The settings page calls the registered function off the UI thread. Until one
is registered, PostgreSQL Test shows a placeholder. SQLite is probed here in
process, read-only, and does not use the seam.
"""

from __future__ import annotations

import os
import socket
import sqlite3
from typing import Callable, Optional

from app.features.form_builder.engine.data.connections import Connection

Tester = Callable[[Connection, Callable[[], str]], dict]

_tester: Optional[Tester] = None

_AUTH = ("28P01", "28000")
_NO_DATABASE = "3D000"


def set_connection_tester(fn: Optional[Tester]) -> None:
    global _tester
    _tester = fn


def connection_tester() -> Optional[Tester]:
    return _tester


def failure_sentence(connection: Connection, kind: str, reason: str) -> str:
    """Settings copy for a failed PostgreSQL test (UX §13.5.9).

    ``unreachable`` is the host-down sentence, including a timeout. The footer
    shows ``reason`` itself, so ``took too long`` stays on that line only.
    """

    if kind == "auth":
        return "The password for %s was not accepted." % (connection.user or "")
    if kind == "unreachable":
        port = connection.port if isinstance(connection.port, int) else 5432
        return (
            "Can't reach %s:%s. Check the address and that the database server is running."
            % (connection.host or "", port)
        )
    if kind == "no_database":
        return "%s has no database named %s." % (connection.host or "", connection.database or "")
    if kind == "no_driver":
        return "No PostgreSQL driver could be loaded (tried psycopg, pg8000)."
    if kind == "cancelled":
        return ""
    return reason or "Can't connect."


def missing_database_sentence(path: str) -> str:
    """One sentence. The path is the reason a missing file could not be opened."""

    shown = path or "that file"
    return "Could not open that database. %s is missing." % shown


def probe_sqlite(path: str) -> str:
    """``✓ Connected · SQLite · {n} tables``, or the first line of the error. A missing file fails."""

    if not path or not os.path.isfile(path):
        return missing_database_sentence(path)
    try:
        connection = sqlite3.connect("file:" + path + "?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            count = int(row[0]) if row else 0
        finally:
            connection.close()
    except Exception as exc:
        text = str(exc).strip().splitlines()
        return text[0] if text else "Can't open the database."
    return "\u2713 Connected · SQLite · %d tables" % count


def classify_connect_error(exc: BaseException) -> str:
    """Map a driver failure to the section 19.7 kind. The password is not logged."""

    state = _sqlstate(exc)
    if state in _AUTH:
        return "auth"
    if state == _NO_DATABASE:
        return "no_database"
    if isinstance(exc, ImportError):
        return "no_driver"
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout, socket.gaierror)):
        return "unreachable"
    low = str(exc).lower()
    # libpq 18 wraps a 9.3 md5 rejection as "connection failed" and drops SQLSTATE.
    # The server text is still the auth failure.
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


def _sqlstate(exc: BaseException) -> str:
    for attr in ("sqlstate", "pgcode"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            return value.upper()
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, dict):
            code = arg.get("C") or arg.get("code") or ""
            if isinstance(code, str) and code:
                return code.upper()
    text = str(exc).upper()
    for code in _AUTH + (_NO_DATABASE,):
        if code in text:
            return code
    return ""
