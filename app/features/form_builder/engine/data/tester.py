"""The PostgreSQL test seam (CONTRACTS.md section 19.7).

The settings page calls the registered function off the UI thread. Until one
is registered, PostgreSQL Test shows a placeholder. SQLite is probed here in
process, read-only, and does not use the seam.
"""

from __future__ import annotations

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


def probe_sqlite(path: str) -> str:
    """``✓ Connected · SQLite · {n} tables``, or the first line of the error. A missing file fails."""

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
