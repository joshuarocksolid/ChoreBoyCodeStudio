"""The host's Try data plan. No PostgreSQL driver is imported here."""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from app.features.form_builder.engine.data.connections import load_connections
from app.features.form_builder.engine.data.schema import read_schema
from app.features.form_builder.engine.data.source import RecordSource, read_data, singular
from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan
from app.features.form_builder.engine.ui4.values import StringValue

_META = "cbcs"
_SCHEMA = "schema"
_NEXTVAL = re.compile(r"nextval\('([^']+)'", re.IGNORECASE)


def plan_for(document: object, project_root: str) -> TryDataPlan:
    """One spec for the form's connection. An unbound form gets an empty plan."""

    source = _source(document)
    if source is None or not getattr(source, "connection", ""):
        return TryDataPlan()
    name = str(source.connection)
    loaded, _problem = load_connections(project_root)
    if loaded is None:
        return _refused_plan(name, "connections.json can't be read.")
    connection = next((item for item in loaded.connections if item.name == name), None)
    if connection is None:
        return _refused_plan(name, "there is no connection with that name.")
    hooks = getattr(source, "hooks", None)
    own = bool(getattr(hooks, "connection", "") or "")
    if own or connection.try_show_sql_only:
        mode = "would_run"
    elif connection.engine == "sqlite":
        mode = "scratch"
    else:
        mode = "rollback"
    word = getattr(source, "record_word", None) or ""
    if not word:
        table = str(getattr(source, "table", "") or "")
        word = singular(table) if table else "record"
    key = str(getattr(source, "key", "") or "id")
    nextval, triggers = _effects(project_root, name)
    sqlite_path = ""
    if connection.engine == "sqlite" and connection.file and project_root:
        sqlite_path = os.path.abspath(os.path.join(project_root, *connection.file.split("/")))
    spec = TryConnectionSpec(
        name=name,
        mode=mode,
        title=connection.title or name,
        file=connection.file or "",
        engine=connection.engine or "sqlite",
        sqlite_path=sqlite_path,
        host=connection.host or "",
        port=int(connection.port or 5432),
        database=connection.database or "",
        user=connection.user or "",
        db_schema=connection.schema or "public",
        record_word=word,
        key=key,
        nextval=tuple(nextval),
        triggers=tuple(triggers),
        own_hook=own,
        password_policy=connection.password or "none",
    )
    payload = {"mode": mode, "scratch": ""}
    pg_mode = "would_run" if mode == "would_run" else "rollback"
    return TryDataPlan(connections=((name, payload),), pg_mode=pg_mode, specs=(spec,))


def _refused_plan(name: str, reason: str) -> TryDataPlan:
    sentence = "Try can't open %s: %s" % (name, reason)
    spec = TryConnectionSpec(name=name, mode="scratch", title=name, refused=sentence)
    return TryDataPlan(connections=((name, {"mode": "scratch"}),), specs=(spec,))


def _source(document: object) -> Optional[object]:
    root = getattr(document, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None:
        return None
    value = getattr(entry, "value", None)
    if not isinstance(value, StringValue) or not value.text.strip():
        return None
    read = read_data(value.text)
    if isinstance(read.value, RecordSource) or getattr(read.value, "connection", ""):
        return read.value
    return None


def _effects(project_root: str, name: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    path = os.path.join(project_root, _META, _SCHEMA, name + ".json")
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError):
        return [], []
    schema, _error = read_schema(text)
    if schema is None:
        return [], []
    nextval: List[Tuple[str, str, str]] = []
    triggers: List[str] = []
    for table in schema.tables:
        if table.triggers:
            triggers.append(table.name)
        for column in table.columns:
            sequence = _sequence_name(column.default)
            if sequence:
                nextval.append((table.name, column.name, sequence))
    return nextval, triggers


def _sequence_name(default: object) -> str:
    if not isinstance(default, str) or "nextval(" not in default.lower():
        return ""
    match = _NEXTVAL.search(default)
    return match.group(1) if match else ""
