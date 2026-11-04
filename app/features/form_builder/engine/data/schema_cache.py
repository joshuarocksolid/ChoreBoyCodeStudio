"""The one writer of ``cbcs/schema/{connection}.json``.

SQLite is read in this process. PostgreSQL goes through the injected runner.
The editor never imports a PostgreSQL driver.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import urllib.parse
import weakref
from dataclasses import dataclass, replace
from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.data.connections import NAME_RE, Connection
from app.features.form_builder.engine.data.schema import (
    Schema,
    read_schema,
    set_schema_reader,
    write_schema,
)
from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file
from app.features.form_builder.engine.data.tester import failure_sentence

# The engine role cannot import app.core. These match PROJECT_META_DIRNAME and PROJECT_SCHEMA_DIRNAME.
_META_DIRNAME = "cbcs"
_SCHEMA_DIRNAME = "schema"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_PROJECT_ROOT = ""
_PROJECT_SLUG = ""
_RUNNER: Optional[object] = None


@dataclass(frozen=True)
class RefreshOutcome:
    ok: bool
    schema: Optional[Schema]
    kind: str
    reason: str
    kept_previous: bool
    cancelled: bool


@dataclass(frozen=True)
class ProbeColumn:
    name: str
    type: str


@dataclass(frozen=True)
class ProbeOutcome:
    ok: bool
    columns: Tuple[ProbeColumn, ...]
    kind: str
    reason: str
    cancelled: bool


def install_schema_reader(project_root: str) -> None:
    """Read ``cbcs/schema`` for this project. A later call replaces the memo."""

    global _PROJECT_ROOT
    root = os.path.abspath(project_root) if project_root else ""
    _PROJECT_ROOT = root
    memos = weakref.WeakKeyDictionary()

    def reader(doc: object, name: str) -> Optional[Schema]:
        text = _read_cache_text(root, name)
        try:
            bucket = memos.get(doc)
        except TypeError:
            return _parse(text)
        if bucket is None:
            bucket = {}
            memos[doc] = bucket
        found = bucket.get(name)
        if found is not None and found[0] == text:
            return found[1]
        schema = _parse(text)
        bucket[name] = (text, schema)
        return schema

    set_schema_reader(reader)


def set_schema_project(root: str) -> None:
    global _PROJECT_ROOT
    _PROJECT_ROOT = os.path.abspath(root) if root else ""


def install_schema_services(project_root: str, slug: str) -> None:
    install_schema_reader(project_root)
    global _PROJECT_SLUG
    _PROJECT_SLUG = slug


def installed_root() -> str:
    return _PROJECT_ROOT


def installed_slug() -> str:
    return _PROJECT_SLUG


def set_schema_runner(runner: Optional[object]) -> None:
    global _RUNNER
    _RUNNER = runner


def refresh(
    project_root: str,
    connection: Connection,
    ask_secret: Callable[[Connection], str],
    *,
    now: Optional[datetime.datetime] = None,
) -> RefreshOutcome:
    """Read one connection and replace the cache only after ``read_schema`` accepts it."""

    if NAME_RE.match(connection.name) is None:
        return RefreshOutcome(False, None, "other", "The connection name can't be used.", True, False)
    previous = _load(project_root, connection.name)
    if connection.engine == "sqlite":
        return _refresh_sqlite(project_root, connection, previous, now)
    reply = _call("schema", project_root, connection, ask_secret)
    if reply is None:
        return RefreshOutcome(
            False,
            previous,
            "no_driver",
            failure_sentence(connection, "no_driver", ""),
            True,
            False,
        )
    return _from_reply(project_root, connection, reply, previous, now)


def probe_select(
    project_root: str,
    connection: Connection,
    sql: str,
    ask_secret: Callable[[Connection], str],
) -> ProbeOutcome:
    """Column names of ``sql``. Does not read or write the cache."""

    if connection.engine == "sqlite":
        return _probe_sqlite(project_root, connection, sql)
    reply = _call("probe_select", project_root, connection, sql, ask_secret)
    if reply is None:
        return ProbeOutcome(False, (), "no_driver", failure_sentence(connection, "no_driver", ""), False)
    return _probe_from_reply(reply)


def cancel_schema_work() -> None:
    runner = _RUNNER
    if runner is None:
        return
    cancel = getattr(runner, "cancel", None)
    if callable(cancel):
        cancel()


def postgres_tester(connection: Connection, ask_secret: Callable[[], str]) -> dict:
    """The settings-page tester. It uses the root from ``install_schema_reader``."""

    root = _PROJECT_ROOT
    if not root:
        return {"ok": False, "kind": "other", "message": "Can't connect."}

    def ask(_connection: Connection) -> str:
        return ask_secret()

    if _RUNNER is None:
        return {"ok": False, "kind": "no_driver", "message": failure_sentence(connection, "no_driver", "")}
    reply = _call("test", root, connection, ask)
    if not isinstance(reply, dict):
        return {"ok": False, "kind": "other", "message": "Can't connect."}
    if reply.get("ok"):
        return {
            "ok": True,
            "server": str(reply.get("server") or ""),
            "tables": int(reply.get("tables") or 0),
            "driver": str(reply.get("driver") or ""),
        }
    kind = str(reply.get("kind") or "other")
    reason = str(reply.get("message") or "")
    return {"ok": False, "kind": kind, "message": failure_sentence(connection, kind, reason)}


def format_read_at(read_at: str) -> str:
    """``2026-11-02T14:02:11`` becomes ``2 Nov 14:02``. Unparseable text is returned."""

    parsed = _parsed(read_at)
    if parsed is None:
        return read_at
    return "%d %s %02d:%02d" % (parsed.day, _MONTHS[parsed.month - 1], parsed.hour, parsed.minute)


def format_read_day(read_at: str) -> str:
    """``2026-11-02T14:02:11`` becomes ``2 Nov``."""

    parsed = _parsed(read_at)
    if parsed is None:
        return read_at
    return "%d %s" % (parsed.day, _MONTHS[parsed.month - 1])


def footer_text(
    schema: Optional[Schema],
    *,
    busy: bool = False,
    failed: bool = False,
    title: str = "",
    reason: str = "",
) -> str:
    """The footer's sentence. The stale clause is a separate label."""

    if busy:
        return "Reading columns\u2026"
    if failed:
        if schema is not None and schema.read_at:
            return "Using columns read %s. Can't reach %s: %s" % (
                format_read_day(schema.read_at),
                title,
                reason,
            )
        return "Columns haven't been read yet. Can't reach %s: %s" % (title, reason)
    if schema is None or not schema.read_at:
        return "Columns haven't been read yet."
    return "Columns read %s" % format_read_at(schema.read_at)


def _refresh_sqlite(
    project_root: str,
    connection: Connection,
    previous: Optional[Schema],
    now: Optional[datetime.datetime],
) -> RefreshOutcome:
    path = _sqlite_path(project_root, connection)
    if not path or not os.path.isfile(path):
        return RefreshOutcome(False, previous, "other", "Can't open the database.", True, False)
    stamp = _stamp(now)
    try:
        schema = read_sqlite_file(path, connection.name, read_at=stamp)
    except Exception as exc:
        lines = str(exc).strip().splitlines()
        return RefreshOutcome(False, previous, "other", lines[0] if lines else "Can't open the database.", True, False)
    stored = _store(project_root, schema)
    if stored is None:
        return RefreshOutcome(False, previous, "other", "The schema couldn't be read.", True, False)
    return RefreshOutcome(True, stored, "", "", False, False)


def _from_reply(
    project_root: str,
    connection: Connection,
    reply: object,
    previous: Optional[Schema],
    now: Optional[datetime.datetime],
) -> RefreshOutcome:
    if not isinstance(reply, dict):
        return RefreshOutcome(False, previous, "other", "Can't connect.", True, False)
    kind = str(reply.get("kind") or "")
    if kind == "cancelled":
        return RefreshOutcome(False, previous, "cancelled", "", True, True)
    if not reply.get("ok"):
        reason = str(reply.get("message") or "")
        if kind == "no_driver":
            reason = failure_sentence(connection, kind, reason)
        return RefreshOutcome(False, previous, kind or "other", reason, True, False)
    schema = _schema_from_payload(reply.get("schema"), connection.name, _stamp(now))
    if schema is None:
        return RefreshOutcome(False, previous, "other", "The schema couldn't be read.", True, False)
    stored = _store(project_root, schema)
    if stored is None:
        return RefreshOutcome(False, previous, "other", "The schema couldn't be read.", True, False)
    return RefreshOutcome(True, stored, "", "", False, False)


def _probe_from_reply(reply: object) -> ProbeOutcome:
    if not isinstance(reply, dict):
        return ProbeOutcome(False, (), "other", "Can't connect.", False)
    if str(reply.get("kind") or "") == "cancelled":
        return ProbeOutcome(False, (), "cancelled", "", True)
    if not reply.get("ok"):
        return ProbeOutcome(
            False,
            (),
            str(reply.get("kind") or "other"),
            str(reply.get("message") or ""),
            False,
        )
    columns = []
    raw = reply.get("columns")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                columns.append(ProbeColumn(str(item.get("name") or ""), str(item.get("type") or "")))
    return ProbeOutcome(True, tuple(columns), "", "", False)


def _probe_sqlite(project_root: str, connection: Connection, sql: str) -> ProbeOutcome:
    path = _sqlite_path(project_root, connection)
    if not path or not os.path.isfile(path):
        return ProbeOutcome(False, (), "other", "Can't open the database.", False)
    uri = "file:%s?mode=ro" % urllib.parse.quote(path)
    try:
        opened = sqlite3.connect(uri, uri=True)
    except Exception as exc:
        lines = str(exc).strip().splitlines()
        return ProbeOutcome(False, (), "other", lines[0] if lines else "Can't open the database.", False)
    try:
        from app.features.form_builder.engine.data.sql import select_subquery, user_sql_for_wrap

        cursor = opened.execute(
            "SELECT * FROM %s LIMIT 0" % select_subquery(user_sql_for_wrap("sqlite", sql))
        )
        description = cursor.description or ()
        columns = tuple(
            ProbeColumn(str(item[0]), "" if item[1] is None else str(item[1])) for item in description
        )
        return ProbeOutcome(True, columns, "", "", False)
    except Exception as exc:
        lines = str(exc).strip().splitlines()
        return ProbeOutcome(False, (), "other", lines[0] if lines else "Can't run that select.", False)
    finally:
        opened.close()


def _schema_from_payload(payload: object, name: str, read_at: str) -> Optional[Schema]:
    if isinstance(payload, str):
        parsed, error = read_schema(payload)
        if error is not None or parsed is None:
            return None
        return replace(parsed, connection=name, read_at=read_at)
    if not isinstance(payload, dict):
        return None
    body = dict(payload)
    body["connection"] = name
    body["readAt"] = read_at
    parsed, error = read_schema(json.dumps(body))
    if error is not None or parsed is None:
        return None
    return parsed


def store_schema(project_root: str, schema: Schema) -> Optional[Schema]:
    """Write one schema through the cache's replace. The dialog uses this."""

    return _store(project_root, schema)


def _store(project_root: str, schema: Schema) -> Optional[Schema]:
    text = write_schema(schema)
    parsed, error = read_schema(text)
    if error is not None or parsed is None:
        return None
    _replace(project_root, schema.connection, text)
    return parsed


def _replace(project_root: str, name: str, text: str) -> None:
    directory = os.path.join(project_root, _META_DIRNAME, _SCHEMA_DIRNAME)
    os.makedirs(directory, exist_ok=True)
    destination = os.path.join(directory, name + ".json")
    temporary = os.path.join(directory, name + ".json.writing")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
        raise


def _load(project_root: str, name: str) -> Optional[Schema]:
    return _parse(_read_cache_text(project_root, name))


def _read_cache_text(project_root: str, name: str) -> str:
    """Missing and unreadable files are empty bytes, so the next call can see a new file."""

    if not project_root or NAME_RE.match(name) is None:
        return ""
    path = os.path.join(project_root, _META_DIRNAME, _SCHEMA_DIRNAME, name + ".json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return ""


def _parse(text: str) -> Optional[Schema]:
    if not text:
        return None
    schema, _error = read_schema(text)
    return schema


def _sqlite_path(project_root: str, connection: Connection) -> str:
    relative = connection.file or ""
    if not relative or not project_root:
        return relative
    return os.path.abspath(os.path.join(project_root, *relative.split("/")))


def _stamp(now: Optional[datetime.datetime]) -> str:
    return (now or datetime.datetime.now()).isoformat(timespec="seconds")


def _parsed(read_at: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.fromisoformat(read_at)
    except ValueError:
        return None


def _call(name: str, *args: object) -> Optional[object]:
    runner = _RUNNER
    if runner is None:
        return None
    method = getattr(runner, name, None)
    if not callable(method):
        return None
    return method(*args)


__all__ = [
    "ProbeColumn",
    "ProbeOutcome",
    "RefreshOutcome",
    "cancel_schema_work",
    "footer_text",
    "format_read_at",
    "format_read_day",
    "install_schema_reader",
    "install_schema_services",
    "installed_root",
    "installed_slug",
    "postgres_tester",
    "probe_select",
    "refresh",
    "set_schema_project",
    "set_schema_runner",
]
