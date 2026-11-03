"""Try's ``cbcs_connections`` substitute (CONTRACTS section 19.10).

One module object lives in ``sys.modules["cbcs_connections"]``. Each Try view
owns its connections and its scratch file. Two forms in the warm child do not
share them. The editor process never imports a PostgreSQL driver: those
imports happen inside ``open_connection`` when a session actually connects.
"""

from __future__ import annotations

import builtins
import contextlib
import contextvars
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import types
import weakref
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import quote

from app.features.form_builder.engine.data.sql import has_extra_statement, sql_without_comments, statement_words
from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart

LOCK_TIMEOUT = "Another user is editing this {record}. Try stopped waiting after 2 seconds."
STATEMENT_TIMEOUT = "This query took longer than 5 seconds, so Try stopped it."
GENERIC_TIMEOUT = "This query took too long, so Try stopped it."
_TIMEOUT_SPAN = re.compile(r"(\d+)\s*(milliseconds|millisecond|ms|seconds|second|secs|sec|s|minutes|minute|min)\b", re.IGNORECASE)
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
_CTE_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|REPLACE|TRUNCATE)\b", re.IGNORECASE)
_CONTROL = {
    "COMMIT", "END", "BEGIN", "START", "ABORT", "PREPARE", "DEALLOCATE",
    "ATTACH", "DETACH", "VACUUM", "REINDEX", "SET", "ALTER", "DROP",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY", "CALL", "DO",
    "ANALYZE", "CLUSTER", "LOCK", "DISCARD", "CHECKPOINT", "COMMENT",
    "SECURITY", "RESET",
}
_MODULE_NAME = "cbcs_connections"
_SKIP_IMPORT = ("app.", "PySide", "shiboken", "importlib", "encodings", "cbcs_connections")
_EXPLAIN_OPTIONS = {
    "ANALYZE", "ANALYSE", "VERBOSE", "COSTS", "BUFFERS", "TIMING", "FORMAT",
    "SETTINGS", "WAL", "SUMMARY", "TRUE", "FALSE", "ON", "OFF",
}
_CLOSED_ENV = "CBCS_TRY_CLOSED"
_secret_asker: Optional[Callable[[str], str]] = None

_current: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("cbcs_try_view", default=None)
_sessions: Dict[str, "TrySession"] = {}
_imported_by: Dict[str, str] = {}
_saved_import: Optional[Callable[..., object]] = None
_conn_raw: "weakref.WeakKeyDictionary[object, object]" = weakref.WeakKeyDictionary()
_cur_raw: "weakref.WeakKeyDictionary[object, object]" = weakref.WeakKeyDictionary()
_cur_owner: "weakref.WeakKeyDictionary[object, object]" = weakref.WeakKeyDictionary()
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


def explain_database_error(
    exc: BaseException,
    record_word: str,
    *,
    try_set_timeout: bool = False,
) -> Optional[str]:
    """The UX sentence for SQLSTATE 55P03 or 57014, or None when it is some other error.

    ``try_set_timeout`` is true when this Try connection set ``statement_timeout``
    to 5 seconds. A 57014 that names some other duration is not that limit.
    """

    state = _sqlstate(exc)
    record = record_word or "record"
    if state == "55P03":
        return LOCK_TIMEOUT.format(record=record)
    if state != "57014":
        return None
    text = _error_text(exc)
    if "lock timeout" in text or "user request" in text:
        return None
    span = _timeout_span_ms(text)
    if span is not None and span != 5000:
        return GENERIC_TIMEOUT
    if "statement timeout" in text or (try_set_timeout and span is None):
        return STATEMENT_TIMEOUT
    return None


def backup_sqlite(source: str, dest: str) -> None:
    """Copy ``source`` with SQLite's backup API so a WAL is included.

    The source is opened read-only. A missing file is refused, and the open
    does not checkpoint a WAL back into the user's database.
    """

    if not source or not os.path.isfile(source):
        raise CbcsConnectionError("Try can't open %s: the file is missing." % (os.path.basename(source or "database")))
    folder = os.path.dirname(dest)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    uri = "file:%s?mode=ro" % quote(os.path.abspath(source), safe="/")
    try:
        origin = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise CbcsConnectionError(
            "Try can't open %s: the file is missing." % os.path.basename(source)
        ) from exc
    try:
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
    _refusals: Dict[str, str] = field(default_factory=dict)
    _shadow: Dict[Tuple[str, object], Dict[str, object]] = field(default_factory=dict)

    def spec(self, name: str) -> TryConnectionSpec:
        found = self.specs.get(name)
        if found is None:
            raise CbcsConnectionError("This project has no connection named %s." % name)
        return found

    def prepare(self) -> None:
        """Make scratch copies before the form's first query.

        A missing file or a refused spec is recorded and never opened. Would-run
        on SQLite uses a scratch copy too, so a write cannot reach the user's file.
        """

        for spec in self.specs.values():
            if spec.refused:
                self._refuse(spec, spec.refused)
                continue
            if not _needs_copy(spec):
                continue
            source = spec.sqlite_path or spec.scratch
            if not source or not os.path.isfile(source):
                self._refuse(spec, "Try can't open %s: the file is missing." % (spec.title or spec.name))
                continue
            if not self._dir:
                self._dir = tempfile.mkdtemp(prefix="cbcs-try-")
            dest = spec.scratch if spec.scratch and spec.sqlite_path else os.path.join(self._dir, spec.name + ".db")
            if os.path.abspath(dest) == os.path.abspath(source):
                dest = os.path.join(self._dir, spec.name + ".db")
            try:
                backup_sqlite(source, dest)
            except CbcsConnectionError as exc:
                self._refuse(spec, str(exc))
                continue
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
        reason = self._refusals.get(spec.name) or spec.refused
        if reason:
            return reason
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
        return spec is not None and spec.mode == "scratch" and not spec.own_hook and not spec.refused

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
        reason = self._refusals.get(name) or spec.refused
        if reason:
            raise CbcsConnectionError(reason)
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
                if _commits(spec):
                    connection.commit()
                else:
                    connection.rollback()
                    if self._wrote and spec.mode == "rollback":
                        self.note(SqlNote(SAVED_ROLLED_BACK, "", (), "saved"))
        except BaseException:
            if outer:
                _rollback(connection)
            raise
        finally:
            self._depth[name] = self._depth.get(name, 0) - 1
            if self._depth.get(name, 0) <= 0:
                self._depth.pop(name, None)
                if outer:
                    self._shadow = {}

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

    def _refuse(self, spec: TryConnectionSpec, sentence: str) -> None:
        self._refusals[spec.name] = sentence
        self.note(SqlNote(sentence, "", (), "warning"))

    def _password_for(self, spec: TryConnectionSpec) -> str:
        password = self._passwords.get(spec.name, "")
        policy = spec.password_policy or "none"
        if password or policy not in ("ask", "machine"):
            return password
        title = spec.title or spec.name
        if _secret_asker is None:
            raise CbcsConnectionError("Try needs the password for %s." % title)
        found = _secret_asker(spec.name) or ""
        if not found:
            raise CbcsConnectionError("Try needs the password for %s." % title)
        self._passwords[spec.name] = found
        return found

    def _open_sqlite(self, spec: TryConnectionSpec) -> sqlite3.Connection:
        if spec.mode in ("scratch", "would_run"):
            path = self._paths.get(spec.name) or spec.scratch or spec.sqlite_path
        else:
            path = spec.sqlite_path or spec.scratch
        if not path:
            raise CbcsConnectionError("Try has no SQLite file for %s." % spec.name)
        connection = sqlite3.connect(path, detect_types=0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _open_postgres(self, spec: TryConnectionSpec) -> object:
        password = self._password_for(spec)
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

    specs = plan_specs(message.data)
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
    _arm_closed(session)
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
        os.environ.pop(_CLOSED_ENV, None)


def end_all() -> None:
    for view_id in list(_sessions):
        end_try(view_id)


def set_secret_asker(asker: Optional[Callable[[str], str]]) -> None:
    """The preview child asks the host once per connection. ``None`` clears it."""

    global _secret_asker
    _secret_asker = asker


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
    Each class in the MRO that defines a method is wrapped on its own, so a
    subclass that overrides ``cbcs_save`` is wrapped too. The flag is stored
    on that class, not inherited.
    """

    for cls in ui_cls.__mro__:
        if cls is object:
            continue
        if "_cbcs_try_bound" in vars(cls):
            continue
        replaced = False
        for name, fn in list(vars(cls).items()):
            if not isinstance(fn, types.FunctionType):
                continue
            if name.startswith("__"):
                continue
            if not (name.startswith("cbcs_") or name.startswith("_cbcs_")):
                continue
            setattr(cls, name, _bound(fn, view_id, name))
            replaced = True
        if replaced:
            setattr(cls, "_cbcs_try_bound", True)


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
            if name in ("cbcs_save", "_cbcs_write"):
                was_new = bool(getattr(self, "_cbcs_new", False))
                keys = list(getattr(self, "_cbcs_keys", []) or [])
                index = getattr(self, "_cbcs_index", -1)
                loaded = _copy_map(getattr(self, "_cbcs_loaded", None))
                saved = _copy_map(getattr(self, "_cbcs_saved_fields", None))
                result = fn(self, *args, **kwargs)
                if result and not writes_stick(view_id):
                    if was_new:
                        setattr(self, "_cbcs_new", True)
                        setattr(self, "_cbcs_keys", keys)
                        setattr(self, "_cbcs_index", index)
                    if loaded is not None:
                        setattr(self, "_cbcs_loaded", loaded)
                    if saved is not None:
                        setattr(self, "_cbcs_saved_fields", saved)
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
    if chosen is None:
        chosen = _view_on_stack()
    if chosen is not None:
        return _sessions.get(chosen)
    if len(_sessions) == 1:
        return next(iter(_sessions.values()))
    return None


def _view_on_stack() -> Optional[str]:
    """The Try view that imported the module now on the stack."""

    frame: Optional[types.FrameType] = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__")
        if isinstance(name, str):
            view = _imported_by.get(name)
            if view is not None:
                return view
        frame = frame.f_back
    return None


def _install_import_hook() -> None:
    """Bind form classes imported while a Try view is current."""

    global _saved_import
    if _saved_import is not None:
        return
    _saved_import = builtins.__import__

    def _hooked(
        name: str,
        globals: Optional[Dict[str, object]] = None,
        locals: Optional[Dict[str, object]] = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        module = _saved_import(name, globals, locals, fromlist, level)  # type: ignore[misc]
        _notice_import(module, fromlist)
        return module

    builtins.__import__ = _hooked  # type: ignore[assignment]


def _remove_import_hook() -> None:
    global _saved_import
    if _saved_import is None:
        return
    builtins.__import__ = _saved_import  # type: ignore[assignment]
    _saved_import = None
    _imported_by.clear()


def _notice_import(module: object, fromlist: Sequence[str]) -> None:
    try:
        view = _current.get()
        if view is None or not _sessions:
            return
        seen: List[object] = [module]
        for item in fromlist:
            if item and item != "*":
                found = getattr(module, item, None)
                if isinstance(found, types.ModuleType):
                    seen.append(found)
        for found in seen:
            name = getattr(found, "__name__", "")
            if not isinstance(name, str) or not name or name.startswith(_SKIP_IMPORT):
                continue
            _imported_by[name] = view
            for value in list(vars(found).values()):
                if isinstance(value, type):
                    bind_form_class(value, view)
    except Exception:
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
    _install_import_hook()


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
    _remove_import_hook()


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


def _needs_copy(spec: TryConnectionSpec) -> bool:
    return spec.engine == "sqlite" and not spec.own_hook and spec.mode in ("scratch", "would_run")


def _commits(spec: TryConnectionSpec) -> bool:
    """Only a SQLite scratch copy is committed. Rollback and would-run never are."""

    return spec.mode == "scratch" and not spec.own_hook and not spec.refused


def _arm_closed(session: TrySession) -> None:
    """While Try is open, the project's real module must not reach a database."""

    refused = [spec.refused for spec in session.specs.values() if spec.refused]
    os.environ[_CLOSED_ENV] = refused[0] if refused else "Try has this database open."


def _copy_map(value: object) -> Optional[Dict[str, object]]:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


class _NoAutocommit:
    """``autocommit`` stays false. Setting it raises."""

    def __get__(self, obj: object, objtype: object = None) -> bool:
        return False

    def __set__(self, obj: object, value: object) -> None:
        raise CbcsConnectionError("Try does not allow autocommit.")


def _refuse_call(self: object, *args: object, **kwargs: object) -> None:
    del self, args, kwargs
    raise CbcsConnectionError("Try does not allow that connection method.")


def _proxy(raw: object, session: TrySession, spec: TryConnectionSpec, *, rollback: bool) -> object:
    del rollback
    raw_module = type(raw).__module__

    def commit(self: object) -> None:
        if _commits(spec):
            raw.commit()  # type: ignore[attr-defined]
        else:
            _rollback_handle(raw)

    def rollback_fn(self: object) -> None:
        _rollback_handle(raw)

    def cursor(self: object) -> object:
        made = _TracingCursor(raw.cursor(), session, spec)  # type: ignore[attr-defined]
        _cur_owner[made] = raw
        return made

    def close(self: object) -> None:
        raw.close()  # type: ignore[attr-defined]

    def execute(self: object, sql: str, params: object = None) -> object:
        made = self.cursor()  # type: ignore[attr-defined]
        if params is None:
            return made.execute(sql)
        return made.execute(sql, params)

    def executemany(self: object, sql: str, seq: object) -> object:
        return self.cursor().executemany(sql, seq)  # type: ignore[attr-defined]

    cls = type(
        "TryConnection",
        (),
        {
            "__module__": raw_module,
            "commit": commit,
            "rollback": rollback_fn,
            "cursor": cursor,
            "close": close,
            "execute": execute,
            "executemany": executemany,
            "autocommit": _NoAutocommit(),
            "set_autocommit": _refuse_call,
            "transaction": _refuse_call,
            "run": _refuse_call,
            "tpc_begin": _refuse_call,
            "tpc_prepare": _refuse_call,
            "tpc_commit": _refuse_call,
            "tpc_rollback": _refuse_call,
            "tpc_recover": _refuse_call,
        },
    )
    proxy = cls()
    _conn_raw[proxy] = raw
    return proxy


class _TracingCursor:
    """Logs every statement. Would-run writes never reach the server."""

    def __init__(self, raw: object, session: TrySession, spec: TryConnectionSpec) -> None:
        _cur_raw[self] = raw
        self._session = session
        self._spec = spec
        self._fake_rowcount: Optional[int] = None
        self._fake_key: Optional[object] = None
        self._fake_row: Optional[Tuple[object, ...]] = None
        self._serving_fake = False
        self._last_sql = ""
        self._last_values: Tuple[object, ...] = ()
        self._held = False
        self._held_rows: Optional[List[object]] = None
        self._held_at = 0
        self._held_rowcount: Optional[int] = None
        self._held_description: object = None
        self._held_lastrowid: object = None

    def execute(self, sql: str, params: object = None) -> object:
        values = _param_tuple(params)
        self._held = False
        self._held_rows = None
        blocked = _blocked_sentence(sql, self._spec)
        if blocked:
            self._session.note(SqlNote(blocked, sql, values, "would_run"))
            self._serving_fake = True
            self._fake_rowcount = 0
            self._fake_key = None
            self._fake_row = None
            return self
        kind = _classify(sql)
        if kind == "control":
            word = _first_word(sql) or "that statement"
            self._session.note(SqlNote("Try did not run %s." % word, sql, values, "would_run"))
            self._serving_fake = True
            self._fake_rowcount = 0
            self._fake_key = None
            self._fake_row = None
            return self
        verb = _verb(sql)
        writing = kind == "write"
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
        driver = _cur_raw[self]
        try:
            if params is None:
                driver.execute(sql)  # type: ignore[attr-defined]
            else:
                driver.execute(sql, params)  # type: ignore[attr-defined]
        except Exception as exc:
            self._release_outside()
            mapped = explain_database_error(
                exc,
                self._spec.record_word,
                try_set_timeout=self._spec.engine == "postgres",
            )
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
        self._release_outside()
        if self._spec.mode == "rollback":
            self._note_nextval(sql)
        return self

    def executemany(self, sql: str, seq: object) -> object:
        rows = list(seq)  # type: ignore[arg-type]
        if _blocked_sentence(sql, self._spec):
            for params in rows:
                self.execute(sql, params)
            return self
        kind = _classify(sql)
        if kind == "control" or (kind == "write" and (self._spec.mode == "would_run" or self._spec.own_hook)):
            for params in rows:
                self.execute(sql, params)
            return self
        driver = _cur_raw[self]
        try:
            driver.executemany(sql, rows)  # type: ignore[attr-defined]
        except Exception as exc:
            self._release_outside()
            mapped = explain_database_error(
                exc,
                self._spec.record_word,
                try_set_timeout=self._spec.engine == "postgres",
            )
            if mapped is not None:
                raise CbcsConnectionError(mapped) from None
            raise
        self._serving_fake = False
        self._fake_rowcount = None
        self._session.note(SqlNote(_sentence("Ran", sql, ()), sql, (), "ran"))
        if kind == "write":
            self._session._wrote = True
        self._release_outside()
        return self

    def fetchmany(self, size: Optional[int] = None) -> object:
        if self._serving_fake:
            return []
        if self._held:
            return self._take(size)
        driver = _cur_raw[self]
        if size is None:
            return driver.fetchmany()  # type: ignore[attr-defined]
        return driver.fetchmany(size)  # type: ignore[attr-defined]

    def close(self) -> None:
        closer = getattr(_cur_raw.get(self), "close", None)
        if callable(closer):
            closer()

    def fetchone(self) -> object:
        if self._serving_fake:
            if self._fake_row is not None:
                row = self._fake_row
                self._fake_row = None
                return row
            if self._fake_key is not None:
                return (self._fake_key,)
            return None
        if self._held:
            found = self._take(1)
            return found[0] if found else None
        row = _cur_raw[self].fetchone()  # type: ignore[attr-defined]
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
        if self._held:
            return self._take(None)
        return _cur_raw[self].fetchall()  # type: ignore[attr-defined]

    @property
    def rowcount(self) -> int:
        if self._fake_rowcount is not None:
            return self._fake_rowcount
        if self._held and self._held_rowcount is not None:
            return self._held_rowcount
        return int(getattr(_cur_raw.get(self), "rowcount", -1))

    @property
    def lastrowid(self) -> object:
        if self._fake_key is not None:
            return self._fake_key
        if self._held:
            return self._held_lastrowid
        return getattr(_cur_raw.get(self), "lastrowid", None)

    @property
    def description(self) -> object:
        if self._held:
            return self._held_description
        return getattr(_cur_raw.get(self), "description", None)

    def _take(self, size: Optional[int]) -> List[object]:
        rows = self._held_rows or []
        if size is None:
            found = rows[self._held_at:]
            self._held_at = len(rows)
            return found
        found = rows[self._held_at:self._held_at + size]
        self._held_at += len(found)
        return found

    def _release_outside(self) -> None:
        """A statement outside ``work()`` must not keep a transaction open."""

        if self._session._depth.get(self._spec.name, 0) > 0:
            return
        driver = _cur_raw.get(self)
        if driver is None:
            return
        self._held_rowcount = int(getattr(driver, "rowcount", -1))
        self._held_description = getattr(driver, "description", None)
        self._held_lastrowid = getattr(driver, "lastrowid", None)
        if self._held_description:
            try:
                self._held_rows = list(driver.fetchall())  # type: ignore[attr-defined]
            except Exception:
                self._held_rows = []
        else:
            self._held_rows = None
        self._held_at = 0
        self._held = True
        _rollback_handle(_cur_owner.get(self))

    def _note_nextval(self, sql: str) -> None:
        if self._spec.engine != "postgres":
            return
        for match in _NEXTVAL.finditer(sql):
            sequence = match.group(1)
            number = self._sequence_value(sequence)
            self._session.warn_once(
                ("seq", sequence),
                SEQUENCE_WARNING.format(n=number, sequence=sequence, record=self._spec.record_word or "record"),
            )

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
        data = None
        shadow = self._session_shadow()
        for value in values:
            found = shadow.get((table, value))
            if found:
                data = found
                break
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
        raw: object = None
        probe: object = None
        value: object = "?"
        try:
            probe = self._session.open_connection(self._spec.name).cursor()  # type: ignore[union-attr]
            found = _cur_raw.get(probe, probe)
            if found is None:
                return "?"
            raw = found
            raw.execute("SAVEPOINT cbcs_try_seq")  # type: ignore[attr-defined]
            raw.execute("SELECT currval(%s::regclass)", (sequence,))  # type: ignore[attr-defined]
            row = raw.fetchone()  # type: ignore[attr-defined]
            raw.execute("RELEASE SAVEPOINT cbcs_try_seq")  # type: ignore[attr-defined]
            if row:
                value = row[0]
        except Exception:
            if raw is not None:
                try:
                    raw.execute("ROLLBACK TO SAVEPOINT cbcs_try_seq")
                except Exception:
                    value = "?"
            value = "?"
        if raw is not None and self._session._depth.get(self._spec.name, 0) == 0:
            _rollback_handle(_cur_owner.get(probe) if probe is not None else None)
        return value


def _set_local(connection: object) -> None:
    cursor = connection.cursor()
    raw = _cur_raw.get(cursor, cursor)
    if raw is None:
        return
    raw.execute("SET LOCAL statement_timeout = '5s'")  # type: ignore[attr-defined]
    raw.execute("SET LOCAL lock_timeout = '2s'")  # type: ignore[attr-defined]


def _rollback(connection: object) -> None:
    _rollback_handle(_conn_raw.get(connection, connection))


def _rollback_handle(raw: object) -> None:
    if raw is None:
        return
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
    cursor.execute("SET statement_timeout = '5s'")
    cursor.execute("SET lock_timeout = '2s'")
    if spec.db_schema and spec.db_schema != "public":
        cursor.execute("SET search_path TO %s" % _quote(spec.db_schema))
    if autocommit is not None:
        raw.autocommit = False  # type: ignore[attr-defined]
    else:
        raw.commit()  # type: ignore[attr-defined]


def _quote(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


def _strip_comments(sql: str) -> str:
    return sql_without_comments(sql)


def _blocked_sentence(sql: str, spec: TryConnectionSpec) -> str:
    """A sentence when this string must not reach the server, else ''."""

    if has_extra_statement(sql):
        return "Try did not run this. Another statement follows the semicolon."
    mode = "would_run" if spec.own_hook or spec.mode == "would_run" else spec.mode
    for name in _call_names(sql):
        if _refused_call(name, mode):
            return "Try did not run %s." % name
    return ""


def _call_names(sql: str) -> Tuple[str, ...]:
    words = statement_words(sql)
    if not words:
        return ()
    found: List[str] = []
    for index, word in enumerate(words):
        if word in (";", "(", ")"):
            continue
        if index + 1 < len(words) and words[index + 1] == "(":
            found.append(word.lower())
    return tuple(found)


def _refused_call(name: str, mode: str) -> bool:
    if name in ("setval", "set_config"):
        return True
    if mode != "would_run":
        return False
    if name in ("nextval", "pg_terminate_backend", "pg_cancel_backend"):
        return True
    if name.startswith("pg_advisory_") or name.startswith("lo_") or name.startswith("dblink"):
        return True
    return False


def _explained_verb(sql: str) -> Optional[str]:
    """The verb under ``EXPLAIN (ANALYZE)``, or None when EXPLAIN does not run it."""

    words = statement_words(sql)
    if not words or words[0].upper() != "EXPLAIN":
        return None
    index = 1
    options: List[str] = []
    if index < len(words) and words[index] == "(":
        depth = 0
        while index < len(words):
            token = words[index]
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                index += 1
                if depth == 0:
                    break
                continue
            else:
                options.append(token.upper())
            index += 1
    else:
        while index < len(words) and words[index].upper() in _EXPLAIN_OPTIONS:
            options.append(words[index].upper())
            index += 1
    if "ANALYZE" not in options and "ANALYSE" not in options:
        return None
    while index < len(words) and words[index] in (";", "(", ")"):
        index += 1
    if index >= len(words):
        return ""
    return words[index].upper()


def _first_word(sql: str) -> str:
    text = _strip_comments(sql)
    if not text:
        return ""
    return text.split(None, 1)[0].rstrip(";").upper()


def _verb(sql: str) -> str:
    return _first_word(sql)


def _classify(sql: str) -> str:
    """``read`` runs. ``write`` runs only outside would-run. ``control`` never runs."""

    word = _first_word(sql)
    if word in ("SAVEPOINT", "RELEASE"):
        return "savepoint"
    if word == "ROLLBACK":
        if " TO " in _strip_comments(sql).upper():
            return "savepoint"
        return "control"
    if word in _CONTROL:
        return "control"
    if word == "PRAGMA":
        return "control" if "=" in _strip_comments(sql) else "read"
    if word == "EXPLAIN":
        verb = _explained_verb(sql)
        if verb is None:
            return "read"
        if not verb:
            return "write"
        if verb in ("SELECT", "SHOW", "VALUES", "TABLE"):
            return "read"
        if verb == "WITH":
            if _CTE_WRITE.search(_strip_comments(sql)):
                return "write"
            return "read"
        if verb in _CONTROL:
            return "control"
        return "write"
    if word == "WITH":
        if _CTE_WRITE.search(_strip_comments(sql)):
            return "write"
        return "read"
    if word in ("SELECT", "SHOW", "VALUES", "TABLE"):
        return "read"
    return "write"


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
    if len(compact) > 40:
        compact = compact[:37] + "…"
    count = len(params)
    if not count:
        return "%s: %s" % (prefix, compact)
    word = "value" if count == 1 else "values"
    return "%s: %s (%d %s)" % (prefix, compact, count, word)


def _error_text(exc: BaseException) -> str:
    parts = [str(exc)]
    diag = getattr(exc, "diag", None)
    if diag is not None:
        for attr in ("message_primary", "message_detail"):
            value = getattr(diag, attr, None)
            if isinstance(value, str):
                parts.append(value)
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], dict):
        for key in ("M", "D"):
            value = args[0].get(key)
            if isinstance(value, str):
                parts.append(value)
    return " ".join(parts).lower()


def _timeout_span_ms(text: str) -> Optional[int]:
    match = _TIMEOUT_SPAN.search(text)
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("ms", "millisecond", "milliseconds"):
        return amount
    if unit in ("min", "minute", "minutes"):
        return amount * 60000
    return amount * 1000


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
