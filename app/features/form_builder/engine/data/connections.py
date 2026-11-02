"""Project connections file (CONTRACTS.md section 19.2).

``connections.json`` is canonical JSON. Defaults are omitted. Unknown keys
are kept in read order and written back after the known ones. A bad file
returns a diagnostic; it does not raise.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data as _fb3xx_data  # noqa: F401
from app.features.form_builder.engine.logic.codec import (
    JsonObject,
    JsonValue,
    Pairs,
    parse_json,
    write_json,
)
from app.features.form_builder.engine.project.fs import OsFileSystem, inside_project

CONNECTIONS_FILENAME = "connections.json"
FB302 = "FB302"

NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
ILLEGAL_NAME_SENTENCE = (
    "Connection names use letters, digits and underscores, and start with a letter or underscore."
)
OUTSIDE_PROJECT_SENTENCE = "Keep the database inside the project so it is packaged with the app."

_KNOWN = (
    "name",
    "title",
    "engine",
    "file",
    "host",
    "port",
    "database",
    "user",
    "password",
    "schema",
    "setup",
    "tryShowSqlOnly",
)
_ENGINES = ("sqlite", "postgres")
_PASSWORDS = ("ask", "machine", "none")
_FORBIDDEN = ("secret", "pw")


@dataclass(frozen=True)
class ConnectionsDiagnostic:
    """A connections file the settings page can show. ``code`` is FB302."""

    code: str
    sentence: str


@dataclass(frozen=True)
class Connection:
    """One named database. Absent defaults are None or False and are not written."""

    name: str
    title: str
    engine: str
    file: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    schema: Optional[str] = None
    setup: Optional[str] = None
    try_show_sql_only: bool = False
    unknown: Pairs = ()


@dataclass(frozen=True)
class ConnectionSet:
    connections: Tuple[Connection, ...] = ()
    unknown: Pairs = ()


def code_name_from_title(title: str) -> str:
    """A code name derived from an on-screen title. Digits are kept; a leading digit is prefixed."""

    chars = []
    for char in title.strip().lower():
        if ("a" <= char <= "z") or ("0" <= char <= "9"):
            chars.append(char)
        elif char == "_":
            chars.append(char)
        elif chars and chars[-1] != "_":
            chars.append("_")
    text = "".join(chars).strip("_")
    if not text:
        text = "connection"
    if text[0].isdigit():
        text = "_" + text
    return text


def read_connections(
    text: str,
    *,
    project_root: Optional[str] = None,
) -> Tuple[Optional[ConnectionSet], Optional[ConnectionsDiagnostic]]:
    """Parse ``connections.json`` text. The second item is set when the file is refused."""

    parsed = parse_json(text)
    if parsed.error is not None or not isinstance(parsed.value, JsonObject):
        sentence = "The connections file can't be read."
        if parsed.error is not None and parsed.error[1] and parsed.error[1] != "not valid JSON":
            sentence = "The connections file can't be read. %s" % parsed.error[1]
        return None, ConnectionsDiagnostic(FB302, sentence)
    return _from_object(parsed.value, project_root)


def write_connections(value: ConnectionSet) -> str:
    """Canonical text, one connection per line, with one trailing newline."""

    pairs = [("version", 1), ("connections", tuple(_connection_object(item) for item in value.connections))]
    pairs.extend(value.unknown)
    return write_json(JsonObject(tuple(pairs))) + "\n"


def load_connections(
    project_root: str,
) -> Tuple[Optional[ConnectionSet], Optional[ConnectionsDiagnostic]]:
    """Read ``<root>/connections.json``. A missing file is an empty set."""

    path = os.path.join(project_root, CONNECTIONS_FILENAME)
    if not os.path.exists(path):
        return ConnectionSet(), None
    try:
        text = OsFileSystem().read_text(path)
    except (OSError, UnicodeError):
        return None, ConnectionsDiagnostic(FB302, "The connections file can't be read.")
    return read_connections(text, project_root=project_root)


def save_connections(project_root: str, value: ConnectionSet) -> None:
    """Atomically replace ``<root>/connections.json``."""

    path = os.path.join(project_root, CONNECTIONS_FILENAME)
    OsFileSystem().write_text(path, write_connections(value))


def _from_object(
    obj: JsonObject,
    project_root: Optional[str],
) -> Tuple[Optional[ConnectionSet], Optional[ConnectionsDiagnostic]]:
    if _forbidden(obj):
        return None, ConnectionsDiagnostic(FB302, "connections.json must not store a secret.")
    known, unknown = _split(obj, ("version", "connections"))
    version = known.get("version")
    if version != 1:
        return None, ConnectionsDiagnostic(FB302, "connections.json version must be 1.")
    raw_rows = known.get("connections")
    if not isinstance(raw_rows, tuple):
        return None, ConnectionsDiagnostic(FB302, "connections.json must list its connections.")
    rows = []
    seen = set()
    for item in raw_rows:
        if not isinstance(item, JsonObject):
            return None, ConnectionsDiagnostic(FB302, "Each connection must be an object.")
        if _forbidden(item):
            return None, ConnectionsDiagnostic(FB302, "connections.json must not store a secret.")
        connection, diagnostic = _connection(item, project_root)
        if diagnostic is not None:
            return None, diagnostic
        assert connection is not None
        if connection.name in seen:
            return None, ConnectionsDiagnostic(
                FB302,
                "Connection name %s is used more than once." % connection.name,
            )
        seen.add(connection.name)
        rows.append(connection)
    return ConnectionSet(tuple(rows), unknown), None


def _connection(
    obj: JsonObject,
    project_root: Optional[str],
) -> Tuple[Optional[Connection], Optional[ConnectionsDiagnostic]]:
    known, unknown = _split(obj, _KNOWN)
    name = known.get("name")
    title = known.get("title")
    engine = known.get("engine")
    if not isinstance(name, str) or not isinstance(title, str) or not isinstance(engine, str):
        return None, ConnectionsDiagnostic(FB302, "A connection needs a name, a title, and an engine.")
    if NAME_RE.match(name) is None:
        return None, ConnectionsDiagnostic(FB302, ILLEGAL_NAME_SENTENCE)
    if engine not in _ENGINES:
        return None, ConnectionsDiagnostic(FB302, "A connection engine must be sqlite or postgres.")
    file_name, host, database, user, schema, setup = (
        known.get("file"),
        known.get("host"),
        known.get("database"),
        known.get("user"),
        known.get("schema"),
        known.get("setup"),
    )
    for label, value in (
        ("file", file_name),
        ("host", host),
        ("database", database),
        ("user", user),
        ("schema", schema),
        ("setup", setup),
    ):
        if value is not None and not isinstance(value, str):
            return None, ConnectionsDiagnostic(FB302, "A connection's %s must be text." % label)
    port, port_error = _port(known.get("port"))
    if port_error is not None:
        return None, port_error
    password, password_error = _password(known.get("password"))
    if password_error is not None:
        return None, password_error
    show_sql, show_error = _flag(known.get("tryShowSqlOnly"))
    if show_error is not None:
        return None, show_error
    if engine == "sqlite":
        file_error = _sqlite_file(file_name if isinstance(file_name, str) else "", project_root)
        if file_error is not None:
            return None, file_error
    else:
        if not _text(host) or not _text(database) or not _text(user):
            return None, ConnectionsDiagnostic(
                FB302,
                "A PostgreSQL connection needs a host, a database, and a user.",
            )
    return (
        Connection(
            name,
            title,
            engine,
            file=_text(file_name),
            host=_text(host),
            port=port,
            database=_text(database),
            user=_text(user),
            password=password,
            schema=None if schema in (None, "", "public") else schema,
            setup=None if setup in (None, "", "none") else setup,
            try_show_sql_only=bool(show_sql),
            unknown=unknown,
        ),
        None,
    )


def _sqlite_file(file_name: str, project_root: Optional[str]) -> Optional[ConnectionsDiagnostic]:
    if not file_name:
        return ConnectionsDiagnostic(FB302, "A SQLite connection needs a file inside the project.")
    parts = file_name.split("/")
    absolute = file_name.startswith("/") or os.path.isabs(file_name) or "\\" in file_name
    if absolute or any(part == ".." for part in parts) or file_name.startswith("/"):
        return ConnectionsDiagnostic(FB302, OUTSIDE_PROJECT_SENTENCE)
    if project_root is not None and not inside_project(os.path.join(project_root, *parts), project_root):
        return ConnectionsDiagnostic(FB302, OUTSIDE_PROJECT_SENTENCE)
    return None


def _port(value: object) -> Tuple[Optional[int], Optional[ConnectionsDiagnostic]]:
    if value is None or value == 5432:
        return None, None
    if isinstance(value, bool) or not isinstance(value, int):
        return None, ConnectionsDiagnostic(FB302, "A connection port must be a whole number.")
    return value, None


def _password(value: object) -> Tuple[Optional[str], Optional[ConnectionsDiagnostic]]:
    if value is None:
        return None, None
    if value not in _PASSWORDS:
        return None, ConnectionsDiagnostic(FB302, "A connection password must be ask, machine, or none.")
    return str(value), None


def _flag(value: object) -> Tuple[bool, Optional[ConnectionsDiagnostic]]:
    if value is None or value is False:
        return False, None
    if value is True:
        return True, None
    return False, ConnectionsDiagnostic(FB302, "tryShowSqlOnly must be true or false.")


def _text(value: object) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    return None


def _split(obj: JsonObject, names: Tuple[str, ...]) -> Tuple[dict, Pairs]:
    known = {}
    unknown = []
    for key, value in obj.pairs:
        if key in names:
            known[key] = value
        else:
            unknown.append((key, value))
    return known, tuple(unknown)


def _forbidden(value: JsonValue) -> bool:
    if isinstance(value, JsonObject):
        for key, item in value.pairs:
            if key in _FORBIDDEN or _forbidden(item):
                return True
        return False
    if isinstance(value, tuple):
        return any(_forbidden(item) for item in value)
    return False


def _connection_object(value: Connection) -> JsonObject:
    pairs = [("name", value.name), ("title", value.title), ("engine", value.engine)]
    if value.file:
        pairs.append(("file", value.file))
    if value.host:
        pairs.append(("host", value.host))
    if value.port is not None and value.port != 5432:
        pairs.append(("port", value.port))
    if value.database:
        pairs.append(("database", value.database))
    if value.user:
        pairs.append(("user", value.user))
    if value.password:
        pairs.append(("password", value.password))
    if value.schema and value.schema != "public":
        pairs.append(("schema", value.schema))
    if value.setup and value.setup != "none":
        pairs.append(("setup", value.setup))
    if value.try_show_sql_only:
        pairs.append(("tryShowSqlOnly", True))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))
