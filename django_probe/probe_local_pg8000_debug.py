#!/usr/bin/env python
"""
Local debug probe: pg8000 + django-pg8000 full-stack validation.
Exercises raw connectivity, encoding edge cases (SQL_ASCII), Django ORM
via django-pg8000, migrations, CRUD, QuerySet ops, and auth models
against local PostgreSQL.
"""
from __future__ import annotations

import codecs
import os
import sys
import traceback

probe_root = "/home/joshua/Documents/RandomDevStuff/ChoreBoyCodeStudio/django_probe"
vendor_dir = probe_root + "/vendor"
results_dir = probe_root + "/results"

for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

os.makedirs(results_dir, exist_ok=True)

PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "postgres"

results: list[str] = []
step_pass = 0
step_fail = 0


def section(title: str) -> None:
    results.append(f"\n[{title}]")
    print(f"\n--- {title} ---")


def ok(label: str, detail: str = "") -> None:
    global step_pass
    suffix = f" ({detail})" if detail else ""
    line = f"  {label}: OK{suffix}"
    results.append(line)
    print(line)
    step_pass += 1


def fail(label: str) -> None:
    global step_fail
    tb = traceback.format_exc()
    line = f"  {label}: FAILED\n{tb}"
    results.append(line)
    print(line)
    step_fail += 1


def abort(msg: str) -> None:
    results.append(f"\n  ABORT: {msg}")
    print(f"\n  ABORT: {msg}")
    write_results()
    sys.exit(1)


def write_results() -> None:
    output = "\n".join(results)
    results_path = os.path.join(results_dir, "probe_local_pg8000_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=" * 60)
print("Local Debug Probe: pg8000 + django-pg8000")
print("=" * 60)

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")

# ── Step 0: Raw pg8000 connectivity ──────────────────────────

section("Step 0: Raw pg8000 connectivity")

try:
    import pg8000
    ok("import pg8000", getattr(pg8000, "__version__", "?"))
except Exception:
    fail("import pg8000")
    abort("pg8000 import failed, cannot continue")

try:
    import pg8000.native
    ok("import pg8000.native")
except Exception:
    fail("import pg8000.native")
    abort("pg8000.native import failed, cannot continue")

try:
    import pg8000.dbapi
    ok("import pg8000.dbapi")
except Exception:
    fail("import pg8000.dbapi")

try:
    import scramp
    ok("import scramp", getattr(scramp, "__version__", "?"))
except Exception:
    fail("import scramp")

try:
    import dateutil
    ok("import dateutil", getattr(dateutil, "__version__", "?"))
except Exception:
    fail("import dateutil")

conn = None
try:
    conn = pg8000.native.Connection(
        user=PG_USER, password=PG_PASSWORD,
        host=PG_HOST, port=PG_PORT, database=PG_DATABASE,
    )
    ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")
except Exception:
    fail("connect")
    abort("Cannot connect to PostgreSQL, cannot continue")

try:
    rows = conn.run("SELECT version()")
    ok("SELECT version()", rows[0][0][:80])
except Exception:
    fail("SELECT version()")

try:
    rows = conn.run("SELECT current_database(), current_user")
    ok("current_database/user", f"db={rows[0][0]}, user={rows[0][1]}")
except Exception:
    fail("current_database/user")

# ── Step 1: Create databases ────────────────────────────────

section("Step 1: Create databases")

try:
    existing = conn.run("SELECT 1 FROM pg_database WHERE datname = 'django_probe'")
    if existing:
        ok("django_probe DB", "already exists")
    else:
        conn.run("COMMIT")
        conn.run("CREATE DATABASE django_probe")
        ok("django_probe DB", "created")
except Exception:
    fail("django_probe DB creation")

try:
    existing = conn.run("SELECT 1 FROM pg_database WHERE datname = 'django_probe_ascii'")
    if existing:
        ok("django_probe_ascii DB", "already exists")
    else:
        conn.run("COMMIT")
        conn.run(
            "CREATE DATABASE django_probe_ascii "
            "ENCODING 'SQL_ASCII' "
            "TEMPLATE template0 "
            "LC_COLLATE 'C' LC_CTYPE 'C'"
        )
        ok("django_probe_ascii DB", "created with SQL_ASCII encoding")
except Exception:
    fail("django_probe_ascii DB creation")

try:
    conn.close()
    ok("close bootstrap connection")
except Exception:
    fail("close bootstrap connection")

# ── Step 2: Encoding edge-case test ──────────────────────────

section("Step 2: Encoding edge-case test (SQL_ASCII)")

ascii_conn = None
try:
    ascii_conn = pg8000.native.Connection(
        user=PG_USER, password=PG_PASSWORD,
        host=PG_HOST, port=PG_PORT, database="django_probe_ascii",
    )
    ok("connect to django_probe_ascii")
except Exception:
    fail("connect to django_probe_ascii")

if ascii_conn is not None:
    raw_encoding = ascii_conn.parameter_statuses.get("client_encoding", "<missing>")
    results.append(f"  raw client_encoding from server: {raw_encoding!r}")
    print(f"  raw client_encoding from server: {raw_encoding!r}")

    from pg8000.converters import PG_PY_ENCODINGS

    try:
        from django_pg8000.base import Info
        info = Info(ascii_conn)
        resolved = info.encoding
        ok("Info.encoding with SQL_ASCII", f"resolved to {resolved!r}")
    except Exception:
        fail("Info.encoding with SQL_ASCII")

    try:
        if raw_encoding and raw_encoding != "<missing>":
            py_enc = PG_PY_ENCODINGS.get(raw_encoding.lower(), raw_encoding)
            codec = codecs.lookup(py_enc)
            ok("manual PG_PY_ENCODINGS lookup", f"{raw_encoding!r} -> {py_enc!r} -> codec={codec.name!r}")
        else:
            results.append("  SKIP: client_encoding was missing, cannot test mapping")
    except Exception:
        fail("manual PG_PY_ENCODINGS lookup")

    try:
        info_none = Info.__new__(Info)
        info_none.con = type("FakeCon", (), {"parameter_statuses": {}})()
        enc = info_none.encoding
        ok("Info.encoding with None client_encoding", f"returned {enc!r}")
    except Exception:
        fail("Info.encoding with None client_encoding")

    try:
        ascii_conn.close()
    except Exception:
        pass
else:
    results.append("  SKIP: could not connect to django_probe_ascii")

# ── Step 3: Django setup ─────────────────────────────────────

section("Step 3: Django setup with django_pg8000")

os.environ["DJANGO_SETTINGS_MODULE"] = "testsite.settings_postgres"

try:
    import django
    django.setup()
    ok("django.setup()", f"Django {django.VERSION}")
except Exception:
    fail("django.setup()")
    abort("Django setup failed, cannot continue")

from django.conf import settings as dj_settings
db_conf = dj_settings.DATABASES["default"]
results.append(f"  Engine: {db_conf['ENGINE']}")
results.append(f"  Database: {db_conf['NAME']}@{db_conf['HOST']}:{db_conf['PORT']}")

if db_conf["ENGINE"] != "django_pg8000":
    results.append("  WARNING: engine is not django_pg8000!")

# ── Step 4: Migrate ──────────────────────────────────────────

section("Step 4: Migrate")

from io import StringIO
from django.core.management import call_command

try:
    out = StringIO()
    call_command("migrate", verbosity=1, stdout=out)
    migrate_output = out.getvalue()
    ok("migrate")
    for line in migrate_output.strip().split("\n")[-5:]:
        results.append(f"    {line}")
except Exception:
    fail("migrate")

# ── Step 5: CRUD ─────────────────────────────────────────────

section("Step 5: CRUD operations")

try:
    from testapp.models import Task

    t = Task.objects.create(title="Local debug probe task", done=False)
    ok("CREATE", f"id={t.id}, title={t.title!r}")

    fetched = Task.objects.get(id=t.id)
    ok("READ", f"title={fetched.title!r}, done={fetched.done}")

    fetched.done = True
    fetched.save()
    updated = Task.objects.get(id=t.id)
    ok("UPDATE", f"done={updated.done}")

    count_before = Task.objects.count()
    updated.delete()
    count_after = Task.objects.count()
    ok("DELETE", f"{count_before} -> {count_after}")
except Exception:
    fail("CRUD")

# ── Step 6: QuerySet operations ──────────────────────────────

section("Step 6: QuerySet operations")

try:
    from testapp.models import Task

    Task.objects.all().delete()
    Task.objects.create(title="Task A", done=False)
    Task.objects.create(title="Task B", done=True)
    Task.objects.create(title="Task C", done=False)
    Task.objects.create(title="Task D", done=True)
    Task.objects.create(title="Task E", done=True)
    ok("bulk insert", "5 tasks created")
except Exception:
    fail("bulk insert")

try:
    done_tasks = Task.objects.filter(done=True)
    ok("filter(done=True)", f"{done_tasks.count()} results")
except Exception:
    fail("filter")

try:
    not_done = Task.objects.exclude(done=True)
    ok("exclude(done=True)", f"{not_done.count()} results")
except Exception:
    fail("exclude")

try:
    ordered = list(Task.objects.order_by("-title").values_list("title", flat=True))
    ok("order_by('-title')", f"{ordered}")
except Exception:
    fail("order_by")

try:
    total = Task.objects.count()
    ok("count()", f"{total}")
except Exception:
    fail("count")

try:
    from django.db.models import Q, Count
    agg = Task.objects.aggregate(
        total=Count("id"),
        done_count=Count("id", filter=Q(done=True)),
    )
    ok("aggregate", f"total={agg['total']}, done={agg['done_count']}")
except Exception:
    fail("aggregate")

try:
    exists = Task.objects.filter(title="Task A").exists()
    ok("exists()", f"{exists}")
except Exception:
    fail("exists")

try:
    first = Task.objects.order_by("id").first()
    last = Task.objects.order_by("id").last()
    ok("first/last", f"first={first.title!r}, last={last.title!r}")
except Exception:
    fail("first/last")

# ── Step 7: Auth model ───────────────────────────────────────

section("Step 7: Built-in auth model")

try:
    from django.contrib.auth.models import User

    User.objects.filter(username="local_probe_user").delete()
    User.objects.create_user("local_probe_user", "probe@test.local", "probe123")
    user_count = User.objects.filter(username="local_probe_user").count()
    ok("create user", f"{user_count} user(s)")
    User.objects.filter(username="local_probe_user").delete()
    ok("delete user")
except Exception:
    fail("auth model")

# ── Step 8: Cleanup ──────────────────────────────────────────

section("Step 8: Cleanup")

try:
    from testapp.models import Task
    deleted_count, _ = Task.objects.all().delete()
    ok("delete all tasks", f"{deleted_count} removed")
except Exception:
    fail("cleanup")

# ── Step 9: System check ─────────────────────────────────────

section("Step 9: System check")

try:
    out = StringIO()
    call_command("check", stdout=out)
    check_output = out.getvalue().strip()
    ok("check", check_output)
except Exception:
    fail("system check")

# ── Summary ──────────────────────────────────────────────────

section("Summary")
results.append(f"  Passed: {step_pass}")
results.append(f"  Failed: {step_fail}")
print(f"  Passed: {step_pass}")
print(f"  Failed: {step_fail}")

write_results()
print("\n" + "=" * 60)
print(f"Done. {step_pass} passed, {step_fail} failed.")
print("=" * 60)

sys.exit(1 if step_fail > 0 else 0)
