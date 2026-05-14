# ChoreBoy Runtime Pitfalls

Lessons learned from running PySide2 desktop applications on the ChoreBoy
desktop runtime. Every issue in this document worked correctly in the
development environment (system Python 3.12, PostgreSQL 16, UTF-8) but failed
on the production ChoreBoy stack (FreeCAD AppRun Python 3.9, PostgreSQL 9.3,
SQL_ASCII encoding).

Use this as a checklist when starting a new ChoreBoy project.

This file mixes two kinds of guidance:

- **Current repo invariants** that the app already depends on today
- **Recommended hardening guidance** that may go beyond the current repo behavior

When the current code intentionally differs, the implementation wins. The main
example is optional integration gateway bootstrap behavior:

- the application's startup/service-bundle layer currently memoizes
  unavailable optional integration gateways as `None` so the UI can start in a
  degraded state
- core database/bootstrap paths still fail loudly when the application cannot
  continue safely

Read the notes below as operational guidance, not as a claim that every
recommended hardening step has already been adopted everywhere in this repo.

---

## Environment comparison

| Aspect              | Development             | ChoreBoy production          |
|---------------------|-------------------------|------------------------------|
| Python              | 3.12 (system)           | 3.9.2 (FreeCAD AppRun)       |
| Qt binding          | (not always loaded)     | PySide2                       |
| PostgreSQL          | 16                      | 9.3                           |
| Database encoding   | UTF-8                   | SQL_ASCII                     |
| psycopg driver      | pip / venv              | vendored via `cb_psycopg`     |
| Database port       | 5432                    | 5435 (typical)                |

---

## A. PostgreSQL 9.3 SQL compatibility

### A-1. `ON CONFLICT` is not available

**Symptom.** `syntax error at or near "ON"` at startup during permission
seeding.

**Root cause.** `ON CONFLICT` was introduced in PostgreSQL 9.5.  The
development database (PG 16) accepts it; the ChoreBoy database (PG 9.3) does
not.

**Fix pattern.** Use a Python-level idempotency check: SELECT first, INSERT
only when the row is absent.

```python
# Good — PG 9.3 safe
existing = repo.list_permission_codes_for_role(role_id)
if permission_code in existing:
    return
executor.execute(
    "INSERT INTO role_permission (role_id, permission_code) VALUES (%s, %s)",
    (role_id, permission_code),
)
```

```sql
-- Bad — fails on PG 9.3
INSERT INTO role_permission (role_id, permission_code)
VALUES (%s, %s)
ON CONFLICT (role_id, permission_code) DO NOTHING;
```

**Prevention.** Treat PostgreSQL 9.3 as the SQL floor.  Avoid `ON CONFLICT`,
`JSONB`, generated columns, and any syntax added after 9.3.  Use the
`classic_link.compat.pg93` forbidden-feature checks in CI and refer to the
classic_link `docs/compatibility.md`.

### A-2. Status enum values must match the database

**Symptom.** `ForeignKeyViolation: insert or update on table "…"
violates foreign key constraint` when transitioning a record to a new status.

**Root cause.** The app's status constant (e.g., `"VOID"`) did not match the
value stored in the target lookup table (e.g., `"VOIDED"`). On a development
database without the full production reference data the mismatch can go
unnoticed.

**Fix pattern.** Validate app-level status constants against the actual FK
lookup table in the production database.

**Prevention.** Add an integration test or startup assertion that confirms
every app status constant exists as a row in the target reference table.

---

## B. SQL_ASCII encoding — bytes vs str

### B-1. psycopg returns `bytes` instead of `str`

**Symptom.** `TypeError: sequence item 0: expected str instance, bytes found`
in string operations, or idempotency checks silently fail because
`"permission.view" in [b"permission.view"]` is `False`.

**Root cause.** When the PostgreSQL database uses the `SQL_ASCII` encoding,
psycopg's `TextLoader` returns `bytes` objects instead of Python `str`.
Development databases using UTF-8 always return `str`, so the mismatch is
invisible until deployment.

**Fix pattern.** Force UTF-8 client encoding on every new connection,
**regardless of the database's server encoding**:

```python
conn = psycopg.connect(dsn)
conn.execute("SET client_encoding TO 'UTF8'")
```

This must be done in **every** connection factory:

- The app's own executor
- The classic_link psycopg3 executor
- The classic_link pg8000 executor
- Any additional integration executor factory

### B-2. Defensive normalization for data already read

**Symptom.** Comparisons between a `str` value and a `bytes` value from the
database silently fail (no exception, just wrong behavior).

**Root cause.** Even after fixing the connection encoding, pre-existing code
paths or cached results may still contain `bytes`.

**Fix pattern.** Add a bytes-to-str normalization step wherever query results
are compared to app-level string constants:

```python
return [
    v.decode("utf-8") if isinstance(v, (bytes, memoryview)) else v
    for v in (row[0] for row in rows)
]
```

**Prevention.** Always set `client_encoding` in the connection factory so
normalization is only needed as a safety net, not the primary defense. Add a
unit test that feeds `bytes` rows into the function and asserts correct
behavior.

---

## C. Vendored dependency bootstrap ordering

### C-1. `psycopg` is not importable until `cb_psycopg.bootstrap()` runs

**Symptom.** `ModuleNotFoundError: No module named 'psycopg'` or gateway
objects silently resolve to `None`, causing `AttributeError: 'NoneType'
object has no attribute '...'` later.

**Root cause.** On ChoreBoy, psycopg is not pip-installed.  It is loaded at
runtime by `cb_psycopg.bootstrap()`, which patches the import machinery,
loads native `.so` files via memfd, and activates the binary implementation.
Any code that does `import psycopg` before bootstrap runs will fail.  If the
failure is caught and swallowed, the gateway stays `None`.

**Fix pattern.**

1. Never write bare `import psycopg` at module level.  Use the `cb_psycopg`
   API (`cb_psycopg.connect(...)` or `cb_psycopg.get_connection(...)`) which
   calls `bootstrap()` internally.
2. Guard gateway consumers against unavailable integrations:

```python
if self._integration_gateway is None:
    raise RuntimeError("Required integration gateway is unavailable")
```

3. Ensure the boot sequence calls `cb_psycopg.bootstrap()` (or
   `cb_sqlalchemy.bootstrap()`, which calls it internally) before any code
   path that touches the database.

**Current repo behavior.** The app takes a split approach today:

- core startup/bootstrap failures still surface immediately
- optional integration gateways may be lazily memoized as unavailable so the
  shell can load and individual features can degrade gracefully

**Recommended hardening direction.** Keep bootstrap ordering explicit and
surface clear errors immediately at the point a required integration is first
used. If the product later decides to make an integration a hard startup
requirement, the service-bundle degradation path is the place to tighten.

---

## D. Qt / PySide2 threading

### D-1. Modifying Qt widgets from a background thread causes SIGSEGV

**Symptom.** `SIGSEGV` in `QBoxLayout::setGeometry` and/or the warning
`QObject::setParent: Cannot set parent, new parent is in a different thread`.

**Root cause.** Qt widgets must only be modified on the main (GUI) thread.
Batch operations run in a `ThreadPoolExecutor`. If the worker function calls a
method that updates the UI (e.g., a `_refresh_view()` which calls `.reload()`
on page widgets), the widget modification happens on the worker thread and
triggers a segfault.

**Fix pattern.** Separate every background-callable function into a "core"
variant with no UI side effects, and a main-thread wrapper that adds the UI
refresh:

```python
def _do_work_core(self, work_item):
    """Pure logic — no UI side effects.  Safe for background threads."""
    return self._service.process(work_item)

def do_work(self, work_item):
    """Process one item and refresh the UI (main thread only)."""
    self._do_work_core(work_item)
    if self._refresh_view is not None:
        self._refresh_view()
    self.load()
```

Batch paths call `_do_work_core` only. When the batch future completes, use a
Qt signal to return to the main thread before touching the UI:

```python
future.add_done_callback(
    lambda f: self._batch_signal_bridge.completed.emit(...)
)
```

**Prevention.**

- Never pass a callback that touches widgets into a `ThreadPoolExecutor`.
- Audit every function called from a worker thread: trace its call graph for
  any Qt widget access.
- Use a signal bridge (a `QObject` subclass with a custom signal) to marshal
  results back to the main thread.

### D-2. Application shutdown: destroy main window before event loop exits

**Symptom.** `SIGSEGV` when closing the application, in
`QOpenGLContext::currentContext()` or `QSurface::~QSurface()` / `QWindow::~QWindow()`,
often during PySide `SignalManager` teardown.

**Root cause.** When the user closes the last window, Qt emits `aboutToQuit` and
the event loop stops. If the main window is only scheduled for deletion via
`deleteLater()` and the event loop never runs again, that deferred deletion
never runs. The window is then destroyed later during Python interpreter
shutdown, when Qt's GUI thread and OpenGL context are already torn down, which
triggers the segfault.

**Fix pattern.** In the `aboutToQuit` handler, after calling `window.deleteLater()`,
call `QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)` so that
deferred deletions are processed on the GUI thread while the application and
Qt internals are still valid. See `packages/choreboy_runtime/bootstrap.py`
`_on_about_to_quit`.

**Prevention.** Ensure the main window (and any top-level windows) are destroyed
by Qt's event loop before the process exits; do not rely on Python/PySide
teardown to destroy them.

---

## E. Shared-connection transaction poisoning

### E-1. Unhandled errors leave the connection in a failed transaction

**Symptom.** After one operation fails (for example, a `ForeignKeyViolation`
during a status transition), every subsequent database operation fails with
`psycopg.errors.InFailedSqlTransaction: current transaction is aborted,
commands ignored until end of transaction block`.

**Root cause.** When a mutation raises an exception inside a transaction and
no `ROLLBACK` is issued, the PostgreSQL connection stays in a "failed
transaction" state. Because the app uses a shared, long-lived
connection, all later operations on that same connection fail.

**Fix pattern.** Wrap every mutation that uses a shared connection in a
try/except with an explicit rollback:

```python
def update_record(self, record_id, payload):
    try:
        apply_update(record_id, payload)
        self.executor.commit()
    except Exception:
        self.executor.rollback()
        raise
```

Apply this to every service and repository method that writes.

**Prevention.**

- Treat rollback-on-error as mandatory for every shared-connection write
  path, not just the ones that have failed in production.
- Consider a context manager or decorator that automatically rolls back on
  exception:

```python
from contextlib import contextmanager

@contextmanager
def transaction_guard(executor):
    try:
        yield
        executor.commit()
    except Exception:
        executor.rollback()
        raise
```

- Add unit tests that simulate executor failures and verify that `rollback()`
  is called.

---

## Quick-reference checklist for new ChoreBoy projects

1. **SQL floor is PG 9.3.** No `ON CONFLICT`, no `JSONB`, no generated
   columns.
2. **Always `SET client_encoding TO 'UTF8'`** on every new connection, in
   every connection factory.
3. **Bootstrap before import.** Never `import psycopg` at module level; use
   `cb_psycopg.connect()` or call `bootstrap()` explicitly first.
4. **Be explicit about degraded integration behavior.** Optional integration
   gateways may currently resolve to unavailable states; required paths should
   still fail clearly and early.
5. **No Qt from worker threads.** Split background-safe "core" logic from
   UI-refreshing wrappers.  Use signal bridges to return to the main thread.
6. **Rollback on every shared-connection error.** Wrap mutations in
   try/except with `executor.rollback()`.
7. **Validate constants against the real database.** Status codes, enum
   values, and FK references must match the production schema, not
   assumptions.
8. **Test with `bytes` inputs.** Add unit tests that simulate SQL_ASCII
   return values (`bytes` instead of `str`) for any code that compares or
   joins query results with app-level strings.
