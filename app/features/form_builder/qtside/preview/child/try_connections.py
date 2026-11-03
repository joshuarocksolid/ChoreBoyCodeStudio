"""Try's ``cbcs_connections`` substitute (CONTRACTS section 19.10).

One module object lives in ``sys.modules["cbcs_connections"]``. Each Try view
owns its connections and its scratch file. Two forms in the warm child do not
share them. The editor process never imports a PostgreSQL driver: those
imports happen inside ``open_connection`` when a session actually connects.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import types
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart

LOCK_TIMEOUT = "Another user is editing this {record}. Try stopped waiting after 2 seconds."
STATEMENT_TIMEOUT = "This query took longer than 5 seconds, so Try stopped it."
SAVED_ROLLED_BACK = "Saved, then rolled back"
OWN_CONNECTION = "This form uses your own connection method, so Try only shows what it would run."
SEQUENCE_WARNING = (
    "Try used number {n} from {sequence}. Rolled-back numbers are skipped, "
    "so the next real {record} gets a later number."
)
TRIGGER_WARNING = "{table} has triggers. Anything they do outside the database isn't rolled back."

_WRITE = {"INSERT", "UPDATE", "DELETE", "REPLACE"}
_QUOTED = re.compile(r'"([^"]+)"')
_INSERT_COLS = re.compile(r"\(([^)]*)\)\s*VALUES", re.IGNORECASE)
_NEXTVAL = re.compile(r"nextval\('([^']+)'", re.IGNORECASE)
_MODULE_NAME = "cbcs_connections"

_current: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("cbcs_try_view", default=None)
_sessions: Dict[str, "TrySession"] = {}
_module: Optional[types.ModuleType] = None
_saved_module: object = None
_pushed = False


@dataclass
class SqlNote:
    """One What ran row. ``values`` are the statement's parameters, in order."""

    sentence: str
    sql: str = ""
    values: Tuple[object, ...] = ()
    kind: str = "ran"


def explain_database_error(exc: BaseException, record_word: str) -> Optional[str]:
    """The UX sentence for SQLSTATE 55P03 or 57014, or None when it is some other error."""

    state = _sqlstate(exc)
    record = record_word or "record"
    if state == "55P03":
        return LOCK_TIMEOUT.format(record=record)
    if state == "57014":
        return STATEMENT_TIMEOUT
    return None


def backup_sqlite(source: str, dest: str) -> None:
    """Copy ``source`` with SQLite's backup API so a WAL is included."""

    folder = os.path.dirname(dest)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    origin = sqlite3.connect(source, uri=False)
    try:
        origin.execute("PRAGMA query_only = ON")
        target = sqlite3.connect(dest)
        try:
            origin.backup(target)
        finally:
            target.close()
    finally:
        origin.close()


def plan_specs(plan: TryDataPlan) -> Tuple[TryConnectionSpec, ...]:
    """``specs`` when the host sent them, otherwise the older connections list."""

    if plan.specs:
        return plan.specs
    found: List[TryConnectionSpec] = []
    for name, payload in plan.connections:
        mode = plan.pg_mode
        scratch = ""
        engine = "postgres" if mode in ("rollback", "would_run") else "sqlite"
        if isinstance(payload, dict):
            raw_mode = payload.get("mode")
            if isinstance(raw_mode, str) and raw_mode:
                mode = raw_mode
            raw_scratch = payload.get("scratch")
            if isinstance(raw_scratch, str):
                scratch = raw_scratch
            raw_engine = payload.get("engine") or payload.get("driver")
            if raw_engine == "sqlite":
                engine = "sqlite"
            elif raw_engine == "postgres":
                engine = "postgres"
        if mode not in ("scratch", "rollback", "would_run"):
            mode = "would_run" if plan.pg_mode == "would_run" else "rollback"
        found.append(
            TryConnectionSpec(
                name=str(name),
                mode=mode,
                scratch=scratch,
                engine=engine,
                sqlite_path=scratch,
            )
        )
    return tuple(found)


def usable(spec: TryConnectionSpec) -> bool:
    """True when this spec has enough to open, or it refuses the database on purpose."""

    if spec.own_hook:
        return True
    if spec.engine == "sqlite" and (spec.sqlite_path or spec.scratch or spec.file):
        return True
    if spec.engine == "postgres" and (spec.host or spec.database):
        return True
    return False


@dataclass
class TrySession:
    """Connections and scratch files for one Try view."""

    view_id: str
    specs: Dict[str, TryConnectionSpec]
    project_root: str = ""
    warning: str = ""
    drivers: Tuple[str, ...] = ("psycopg", "pg8000")
    notes: List[SqlNote] = field(default_factory=list)
    on_sql: Optional[Callable[[SqlNote], None]] = None
    _open: Dict[str, object] = field(default_factory=dict)
    _depth: Dict[str, int] = field(default_factory=dict)
    _passwords: Dict[str, str] = field(default_factory=dict)
    _once: set = field(default_factory=set)
    _dir: str = ""
    _paths: Dict[str, str] = field(default_factory=dict)
    _wrote: bool = False
    _key_seq: int = 1000000000

    def spec(self, name: str) -> TryConnectionSpec:
        found = self.specs.get(name)
        if found is None:
            raise CbcsConnectionError("This project has no connection named %s." % name)
        return found

    def prepare(self) -> None:
        """Make scratch copies before the form's first query."""

        for spec in self.specs.values():
            if spec.mode != "scratch":
                continue
            source = spec.sqlite_path or spec.scratch
            if not source:
                raise CbcsConnectionError("Try has no SQLite file for %s." % spec.name)
            if not self._dir:
                self._dir = tempfile.mkdtemp(prefix="cbcs-try-")
            dest = spec.scratch if spec.scratch and spec.sqlite_path else os.path.join(self._dir, spec.name + ".db")
            if os.path.abspath(dest) == os.path.abspath(source):
                dest = os.path.join(self._dir, spec.name + ".db")
            backup_sqlite(source, dest)
            self._paths[spec.name] = dest

    def reset_scratch(self) -> None:
        """Replace the scratch file from the original database and drop the open handle."""

        for spec in list(self.specs.values()):
            if spec.mode != "scratch":
                continue
            self._close_name(spec.name)
            source = spec.sqlite_path
            dest = self._paths.get(spec.name)
            if source and dest:
                backup_sqlite(source, dest)

    def close(self) -> None:
        """Roll back anything still open, close it, and delete the scratch copy."""

        for name in list(self._open):
            self._close_name(name)
        keep = any(spec.keep_scratch for spec in self.specs.values())
        if self._dir and not keep:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = ""
            self._paths.clear()

    def strip_text(self) -> str:
        spec = self._primary()
        if spec is None:
            return ""
        if spec.own_hook:
            return "Data: " + OWN_CONNECTION
        if spec.mode == "scratch":
            shown = spec.file or os.path.basename(spec.sqlite_path or spec.scratch or "database")
            return "Data: scratch copy of %s" % shown
        title = spec.title or spec.name or "the database"
        if spec.mode == "would_run":
            return "Data: %s. Only the SQL is shown." % title
        return "Data: %s. Changes are rolled back." % title

    def banner_text(self) -> str:
        spec = self._primary()
        if spec is None or spec.mode != "rollback" or spec.own_hook:
            return ""
        title = spec.title or spec.name or "the database"
        return (
            "Try: changes to %s are rolled back. While a save runs, other people using it may wait up to 2 seconds."
            % title
        )

    def scratch_file(self, name: str) -> str:
        return self._paths.get(name, "")

    def show_reset(self) -> bool:
        spec = self._primary()
        return spec is not None and spec.mode == "scratch" and not spec.own_hook
        spec = self._primary()
        return spec is not None and spec.mode == "scratch" and not spec.own_hook

    def set_password(self, name: str, password: str) -> None:
        self._passwords[name] = password

    def dialect(self, name: str) -> str:
        engine = self.spec(name).engine
        if engine not in ("sqlite", "postgres"):
            raise CbcsConnectionError("Connection %s has no known engine." % name)
        return engine

    def open_connection(self, name: str) -> object:
        existing = self._open.get(name)
        if existing is not None:
            return existing
        spec = self.spec(name)
        if spec.own_hook:
            connection = _proxy(sqlite3.connect(":memory:"), self, spec, rollback=True)
            self._open[name] = connection
            return connection
        if spec.engine == "sqlite":
            raw = self._open_sqlite(spec)
            rollback = spec.mode == "rollback"
        else:
            raw = self._open_postgres(spec)
            rollback = spec.mode == "rollback"
        connection = _proxy(raw, self, spec, rollback=rollback)
        self._open[name] = connection
        return connection

    @contextlib.contextmanager
    def work(self, name: str) -> Iterator[object]:
        """Outermost block commits, or rolls back. Rollback mode never commits."""

        connection = self.open_connection(name)
        spec = self.spec(name)
        outer = self._depth.get(name, 0) == 0
        self._depth[name] = self._depth.get(name, 0) + 1
        if outer:
            self._wrote = False
            if spec.mode == "rollback" and spec.engine == "postgres" and not spec.own_hook:
                _set_local(connection)
        try:
            yield connection
            if outer:
                if spec.mode == "rollback":
                    connection.rollback()
                    if self._wrote:
                        self.note(SqlNote(SAVED_ROLLED_BACK, "", (), "saved"))
                else:
                    connection.commit()
        except BaseException:
            if outer:
                _rollback(connection)
            raise
        finally:
            self._depth[name] = self._depth.get(name, 0) - 1
            if self._depth.get(name, 0) <= 0:
                self._depth.pop(name, None)

    def close_all(self) -> None:
        for name in list(self._open):
            self._close_name(name)

    def note(self, item: SqlNote) -> None:
        self.notes.append(item)
        if self.on_sql is not None:
            self.on_sql(item)

    def warn_once(self, key: Tuple[str, str], sentence: str) -> None:
        if key in self._once:
            return
        self._once.add(key)
        self.note(SqlNote(sentence, "", (), "warning"))

    def next_key(self) -> int:
        self._key_seq += 1
        return self._key_seq

    def _primary(self) -> Optional[TryConnectionSpec]:
        if not self.specs:
            return None
        return next(iter(self.specs.values()))

    def _open_sqlite(self, spec: TryConnectionSpec) -> sqlite3.Connection:
        if spec.mode == "scratch":
            path = self._paths.get(spec.name) or spec.scratch or spec.sqlite_path
        else:
            path = spec.sqlite_path or spec.scratch
        if not path:
            raise CbcsConnectionError("Try has no SQLite file for %s." % spec.name)
        connection = sqlite3.connect(path, detect_types=0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _open_postgres(self, spec: TryConnectionSpec) -> object:
        password = self._passwords.get(spec.name, "")
        errors: List[str] = []
        for driver in self.drivers:
            try:
                raw = _connect_driver(driver, spec, password)
            except ImportError as exc:
                errors.append("%s: %s" % (driver, exc))
                continue
            except Exception as exc:
                message = str(exc)
                if password and password in message:
                    message = "the database refused the connection"
                raise CbcsConnectionError(message) from None
            _prepare_postgres(raw, spec)
            return raw
        raise CbcsConnectionError("No PostgreSQL driver could be loaded (%s)." % "; ".join(errors))

    def _close_name(self, name: str) -> None:
        connection = self._open.pop(name, None)
        self._depth.pop(name, None)
        if connection is None:
            return
        _rollback(connection)
        try:
            connection.close()
        except Exception:
            return None
        return None


class CbcsConnectionError(Exception):
    """A Try connection could not be opened."""


def begin_try(message: TryStart, *, drivers: Optional[Sequence[str]] = None) -> Optional[TrySession]:
    """Install the substitute for ``message.view_id``. None when the plan has nothing to open."""

    specs = tuple(spec for spec in plan_specs(message.data) if usable(spec))
    if not specs:
        return None
    end_try(message.view_id)
    session = TrySession(
        view_id=message.view_id,
        specs={spec.name: spec for spec in specs},
        project_root=message.project_root or "",
        warning=message.data.warning,
        drivers=tuple(drivers) if drivers else ("psycopg", "pg8000"),
    )
    session.prepare()
    _sessions[message.view_id] = session
    _install_module()
    if spec_own(session):
        session.note(SqlNote(OWN_CONNECTION, "", (), "warning"))
    return session


def end_try(view_id: str) -> None:
    """Close that view's connections and scratch file. The module stays while another view is open."""

    session = _sessions.pop(view_id, None)
    if session is not None:
        session.close()
    if not _sessions:
        _restore_module()


def end_all() -> None:
    for view_id in list(_sessions):
        end_try(view_id)


def remember_password(name: str, password: str) -> None:
    """Store a secret the host just provided. It is not written to a log."""

    for session in _sessions.values():
        if name in session.specs:
            session.set_password(name, password)


def session_for(view_id: str) -> Optional[TrySession]:
    return _sessions.get(view_id)


def activate(view_id: str) -> contextlib.AbstractContextManager[None]:
    """Make ``view_id`` the session ``cbcs_connections`` uses until the block ends."""

    return _activate(view_id)


def bind_form_class(ui_cls: type, view_id: str) -> None:
    """Point this form's database methods at ``view_id``.

    A rolled-back save of a new record keeps ``form.isNew`` and does not add
    the key. A rolled-back delete leaves the key list and shows the real row.
    Generated source is unchanged: the wrap happens on the class the child exec'd.
    """

    if getattr(ui_cls, "_cbcs_try_bound", False):
        return
    setattr(ui_cls, "_cbcs_try_bound", True)
    for name, fn in list(vars(ui_cls).items()):
        if not isinstance(fn, types.FunctionType):
            continue
        if name.startswith("__"):
            continue
        if not (name.startswith("cbcs_") or name.startswith("_cbcs_")):
            continue
        setattr(ui_cls, name, _bound(fn, view_id, name))


def writes_stick(view_id: Optional[str] = None) -> bool:
    """False in rollback mode, where a save must not stick in the form's key list."""

    session = _lookup(view_id)
    if session is None:
        return True
    return all(spec.mode != "rollback" for spec in session.specs.values())


@contextlib.contextmanager
def _activate(view_id: str) -> Iterator[None]:
    token = _current.set(view_id)
    try:
        yield
    finally:
        _current.reset(token)


def _bound(fn: types.FunctionType, view_id: str, name: str) -> types.FunctionType:
    def wrapped(self: object, *args: object, **kwargs: object) -> object:
        token = _current.set(view_id)
        try:
            if name == "cbcs_save":
                was_new = bool(getattr(self, "_cbcs_new", False))
                keys = list(getattr(self, "_cbcs_keys", []) or [])
                index = getattr(self, "_cbcs_index", -1)
                result = fn(self, *args, **kwargs)
                if result and was_new and not writes_stick(view_id):
                    setattr(self, "_cbcs_new", True)
                    setattr(self, "_cbcs_keys", keys)
                    setattr(self, "_cbcs_index", index)
                return result
            if name == "cbcs_delete":
                keys = list(getattr(self, "_cbcs_keys", []) or [])
                index = getattr(self, "_cbcs_index", -1)
                result = fn(self, *args, **kwargs)
                if result and keys and not writes_stick(view_id):
                    setattr(self, "_cbcs_keys", keys)
                    show = getattr(self, "_cbcs_show", None)
                    if callable(show):
                        show(index)
                return result
            return fn(self, *args, **kwargs)
        finally:
            _current.reset(token)

    wrapped.__name__ = name
    return wrapped


def _lookup(view_id: Optional[str] = None) -> Optional[TrySession]:
    chosen = view_id if view_id is not None else _current.get()
    if chosen is not None:
        return _sessions.get(chosen)
    if len(_sessions) == 1:
        return next(iter(_sessions.values()))
    return None


def _require() -> TrySession:
    session = _lookup()
    if session is None:
        raise CbcsConnectionError("Try has no data session for this form.")
    return session


def _install_module() -> None:
    global _module, _saved_module, _pushed
    if not _pushed:
        _saved_module = sys.modules.get(_MODULE_NAME)
        _pushed = True
    if _module is None:
        _module = _build_module()
    sys.modules[_MODULE_NAME] = _module


def _restore_module() -> None:
    global _module, _saved_module, _pushed
    if not _pushed:
        return
    current = sys.modules.get(_MODULE_NAME)
    if current is _module:
        if _saved_module is None:
            sys.modules.pop(_MODULE_NAME, None)
        else:
            sys.modules[_MODULE_NAME] = _saved_module  # type: ignore[assignment]
    _module = None
    _saved_module = None
    _pushed = False


def _build_module() -> types.ModuleType:
    module = types.ModuleType(_MODULE_NAME)
    module.__file__ = "<%s>" % _MODULE_NAME
    module._cbcs_try = True  # type: ignore[attr-defined]

    def project_root() -> str:
        session = _lookup()
        return session.project_root if session is not None else ""

    def dialect(name: str) -> str:
        return _require().dialect(name)

    def set_password(name: str, password: str) -> None:
        _require().set_password(name, password)

    def open_connection(name: str) -> object:
        return _require().open_connection(name)

    def close_all() -> None:
        session = _lookup()
        if session is not None:
            session.close_all()

    def work(name: str) -> object:
        return _require().work(name)

    def text_value(value: object) -> object:
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def writes_stick(name: str = "") -> bool:
        del name
        return writes_stick_view()

    module.CbcsConnectionError = CbcsConnectionError  # type: ignore[attr-defined]
    module.PROJECT_ROOT = project_root  # type: ignore[attr-defined]
    module.dialect = dialect  # type: ignore[attr-defined]
    module.set_password = set_password  # type: ignore[attr-defined]
    module.open_connection = open_connection  # type: ignore[attr-defined]
    module.close_all = close_all  # type: ignore[attr-defined]
    module.work = work  # type: ignore[attr-defined]
    module.text_value = text_value  # type: ignore[attr-defined]
    module.writes_stick = writes_stick  # type: ignore[attr-defined]
    return module


def writes_stick_view() -> bool:
    return writes_stick()


def spec_own(session: TrySession) -> bool:
    return any(spec.own_hook for spec in session.specs.values())


def _proxy(raw: object, session: TrySession, spec: TryConnectionSpec, *, rollback: bool) -> object:
    raw_module = type(raw).__module__

    def commit(self: object) -> None:
        if rollback:
            _rollback(self)
        else:
            self._raw.commit()  # type: ignore[attr-defined]

    def rollback_fn(self: object) -> None:
        _rollback(self)

    def cursor(self: object) -> object:
        return _TracingCursor(self._raw.cursor(), session, spec)  # type: ignore[attr-defined]

    def close(self: object) -> None:
        self._raw.close()  # type: ignore[attr-defined]

    def getattr_fn(self: object, name: str) -> object:
        return getattr(self._raw, name)  # type: ignore[attr-defined]

    cls = type(
        "TryConnection",
        (),
        {
            "__module__": raw_module,
            "commit": commit,
            "rollback": rollback_fn,
            "cursor": cursor,
            "close": close,
            "__getattr__": getattr_fn,
        },
    )
    proxy = cls()
    proxy._raw = raw  # type: ignore[attr-defined]
    proxy._session = session  # type: ignore[attr-defined]
    proxy._spec = spec  # type: ignore[attr-defined]
    return proxy


class _TracingCursor:
    """Logs every statement. Would-run writes never reach the server."""

    def __init__(self, raw: object, session: TrySession, spec: TryConnectionSpec) -> None:
        self._raw = raw
        self._session = session
        self._spec = spec
        self._fake_rowcount: Optional[int] = None
        self._fake_key: Optional[object] = None
        self._fake_row: Optional[Tuple[object, ...]] = None
        self._serving_fake = False
        self._last_sql = ""
        self._last_values: Tuple[object, ...] = ()

    def execute(self, sql: str, params: object = None) -> object:
        values = _param_tuple(params)
        verb = _verb(sql)
        writing = verb in _WRITE
        would = self._spec.own_hook or (self._spec.mode == "would_run" and writing)
        read_only_log = self._spec.own_hook and not writing
        if would or read_only_log:
            prefix = "Would run"
            self._session.note(SqlNote(_sentence(prefix, sql, values), sql, values, "would_run"))
            self._fake_rowcount = 1 if writing else 0
            self._fake_key = None
            self._fake_row = None
            self._serving_fake = True
            if writing:
                self._remember_write(verb, sql, values)
            elif self._point(sql, values) is not None:
                self._fake_row = self._point(sql, values)
            return self
        try:
            if params is None:
                self._raw.execute(sql)  # type: ignore[attr-defined]
            else:
                self._raw.execute(sql, params)  # type: ignore[attr-defined]
        except Exception as exc:
            mapped = explain_database_error(exc, self._spec.record_word)
            if mapped is not None:
                raise CbcsConnectionError(mapped) from None
            raise
        self._serving_fake = False
        self._fake_rowcount = None
        self._fake_key = None
        self._fake_row = None
        self._last_sql = sql
        self._last_values = values
        self._session.note(SqlNote(_sentence("Ran", sql, values), sql, values, "ran"))
        if writing:
            self._session._wrote = True
            self._effects(verb, sql, values)
        return self

    def fetchone(self) -> object:
        if self._serving_fake:
            if self._fake_row is not None:
                row = self._fake_row
                self._fake_row = None
                return row
            if self._fake_key is not None:
                return (self._fake_key,)
            return None
        row = self._raw.fetchone()  # type: ignore[attr-defined]
        if self._spec.mode == "would_run" or self._spec.own_hook:
            overlaid = self._overlay(self._last_sql, self._last_values, row)
            if overlaid is not None:
                return overlaid
        return row

    def fetchall(self) -> object:
        if self._serving_fake:
            if self._fake_row is not None:
                row = self._fake_row
                self._fake_row = None
                return [row]
            return []
        return self._raw.fetchall()  # type: ignore[attr-defined]

    @property
    def rowcount(self) -> int:
        if self._fake_rowcount is not None:
            return self._fake_rowcount
        return int(getattr(self._raw, "rowcount", -1))

    @property
    def lastrowid(self) -> object:
        if self._fake_key is not None:
            return self._fake_key
        return getattr(self._raw, "lastrowid", None)

    @property
    def description(self) -> object:
        return getattr(self._raw, "description", None)

    def __getattr__(self, name: str) -> object:
        return getattr(self._raw, name)

    def _remember_write(self, verb: str, sql: str, values: Tuple[object, ...]) -> None:
        table = _table(sql)
        key_name = self._spec.key or "id"
        if verb == "INSERT":
            columns = _insert_columns(sql)
            data = {column: values[index] for index, column in enumerate(columns) if index < len(values)}
            if key_name in data:
                key = data[key_name]
            else:
                key = self._session.next_key()
                data[key_name] = key
            self._session_shadow()[(table, key)] = data
            self._fake_key = key
            return
        if verb == "UPDATE":
            columns = _set_columns(sql)
            if not columns or len(values) < len(columns):
                return
            key = values[len(columns)]
            data = dict(self._session_shadow().get((table, key), {}))
            for index, column in enumerate(columns):
                data[column] = values[index]
            data.setdefault(key_name, key)
            self._session_shadow()[(table, key)] = data
            return
        if verb == "DELETE" and values:
            self._session_shadow().pop((table, values[0]), None)

    def _overlay(self, sql: str, values: Tuple[object, ...], real: object) -> Optional[Tuple[object, ...]]:
        if _verb(sql) != "SELECT" or not values:
            return None
        table = _table(sql)
        data = self._session_shadow().get((table, values[-1]))
        if not data:
            return None
        columns = _select_columns(sql)
        if not columns:
            return None
        if not isinstance(real, tuple):
            return tuple(data.get(column) for column in columns)
        merged: List[object] = []
        for index, column in enumerate(columns):
            if column in data:
                merged.append(data[column])
            elif index < len(real):
                merged.append(real[index])
            else:
                merged.append(None)
        return tuple(merged)

    def _point(self, sql: str, values: Tuple[object, ...]) -> Optional[Tuple[object, ...]]:
        return self._overlay(sql, values, None)

    def _session_shadow(self) -> Dict[Tuple[str, object], Dict[str, object]]:
        shadow = getattr(self._session, "_shadow", None)
        if shadow is None:
            shadow = {}
            setattr(self._session, "_shadow", shadow)
        return shadow

    def _effects(self, verb: str, sql: str, values: Tuple[object, ...]) -> None:
        table = _table(sql)
        if table and table in self._spec.triggers:
            self._session.warn_once(
                ("trg", table),
                TRIGGER_WARNING.format(table=table),
            )
        if verb != "INSERT":
            return
        columns = set(_insert_columns(sql))
        for entry in self._spec.nextval:
            if len(entry) != 3:
                continue
            entry_table, column, sequence = entry
            if entry_table != table or column in columns or not sequence:
                continue
            number = self._sequence_value(sequence)
            self._session.warn_once(
                ("seq", sequence),
                SEQUENCE_WARNING.format(n=number, sequence=sequence, record=self._spec.record_word or "record"),
            )

    def _sequence_value(self, sequence: str) -> object:
        if self._spec.engine != "postgres":
            return self.lastrowid if self.lastrowid is not None else "?"
        raw = None
        try:
            probe = self._session.open_connection(self._spec.name).cursor()  # type: ignore[union-attr]
            raw = getattr(probe, "_raw", probe)
            raw.execute("SAVEPOINT cbcs_try_seq")
            raw.execute("SELECT currval(%s::regclass)", (sequence,))
            row = raw.fetchone()
            raw.execute("RELEASE SAVEPOINT cbcs_try_seq")
        except Exception:
            if raw is not None:
                try:
                    raw.execute("ROLLBACK TO SAVEPOINT cbcs_try_seq")
                except Exception:
                    return "?"
            return "?"
        if not row:
            return "?"
        return row[0]


def _session_shadow_init() -> None:
    return None


def _set_local(connection: object) -> None:
    cursor = connection.cursor()
    raw = getattr(cursor, "_raw", cursor)
    raw.execute("SET LOCAL statement_timeout = '5s'")
    raw.execute("SET LOCAL lock_timeout = '2s'")


def _rollback(connection: object) -> None:
    raw = getattr(connection, "_raw", connection)
    method = getattr(raw, "rollback", None)
    if callable(method):
        try:
            method()
        except Exception:
            return None
    return None


def _connect_driver(driver: str, spec: TryConnectionSpec, password: str) -> object:
    port = int(spec.port or 5432)
    if driver == "psycopg":
        import psycopg  # type: ignore[import]

        connection = psycopg.connect(
            host=spec.host or "127.0.0.1",
            port=port,
            dbname=spec.database,
            user=spec.user,
            password=password,
        )
        connection.autocommit = False
        return connection
    if driver == "pg8000":
        import pg8000.dbapi as pg8000  # type: ignore[import]

        return pg8000.connect(
            user=spec.user,
            password=password,
            host=spec.host or "127.0.0.1",
            database=spec.database,
            port=port,
        )
    raise ImportError(driver)


def _prepare_postgres(raw: object, spec: TryConnectionSpec) -> None:
    autocommit = getattr(raw, "autocommit", None)
    if autocommit is not None:
        raw.autocommit = True  # type: ignore[attr-defined]
    cursor = raw.cursor()  # type: ignore[attr-defined]
    cursor.execute("SET client_encoding TO 'UTF8'")
    if spec.db_schema and spec.db_schema != "public":
        cursor.execute("SET search_path TO %s" % _quote(spec.db_schema))
    if autocommit is not None:
        raw.autocommit = False  # type: ignore[attr-defined]
    else:
        raw.commit()  # type: ignore[attr-defined]


def _quote(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


def _verb(sql: str) -> str:
    text = sql.lstrip()
    while text.startswith("--"):
        parts = text.split("\n", 1)
        text = parts[1].lstrip() if len(parts) == 2 else ""
    if not text:
        return ""
    return text.split(None, 1)[0].upper()


def _table(sql: str) -> str:
    match = re.search(r'\b(?:FROM|INTO|UPDATE)\s+"([^"]+)"', sql, re.IGNORECASE)
    if match is not None:
        return match.group(1)
    return ""


def _insert_columns(sql: str) -> Tuple[str, ...]:
    match = _INSERT_COLS.search(sql)
    if match is None:
        return ()
    return tuple(_QUOTED.findall(match.group(1)))


def _select_columns(sql: str) -> Tuple[str, ...]:
    upper = sql.upper()
    start = upper.find("SELECT")
    end = upper.find("FROM")
    if start < 0 or end < 0 or end <= start:
        return ()
    return tuple(_QUOTED.findall(sql[start:end]))


def _set_columns(sql: str) -> Tuple[str, ...]:
    upper = sql.upper()
    start = upper.find("SET")
    end = upper.find("WHERE")
    if start < 0:
        return ()
    body = sql[start:end] if end > start else sql[start:]
    return tuple(_QUOTED.findall(body))


def _param_tuple(params: object) -> Tuple[object, ...]:
    if params is None:
        return ()
    if isinstance(params, dict):
        return tuple(params.values())
    if isinstance(params, (list, tuple)):
        return tuple(params)
    return (params,)


def _sentence(prefix: str, sql: str, params: Tuple[object, ...]) -> str:
    compact = " ".join(sql.split())
    if len(compact) > 72:
        compact = compact[:69] + "…"
    count = len(params)
    word = "value" if count == 1 else "values"
    return "%s: %s (%d %s)" % (prefix, compact, count, word)


def _sqlstate(exc: BaseException) -> str:
    for attr in ("sqlstate", "pgcode"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            return value
    diag = getattr(exc, "diag", None)
    if diag is not None:
        value = getattr(diag, "sqlstate", None)
        if isinstance(value, str) and value:
            return value
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], dict):
        code = args[0].get("C") or args[0].get("c")
        if isinstance(code, str) and code:
            return code
    text = str(exc)
    if "55P03" in text:
        return "55P03"
    if "57014" in text:
        return "57014"
    return ""


def sequence_name(default: Optional[str]) -> str:
    """The sequence inside a ``nextval('…')`` default, or ''."""

    if not default or "nextval(" not in default.lower():
        return ""
    match = _NEXTVAL.search(default)
    return match.group(1) if match else ""
