#!/usr/bin/env python
"""
Probe 7: Django ORM with PostgreSQL via django-pg8000
Tests whether Django's ORM can run migrations, CRUD, auth models,
and queryset operations against PostgreSQL using the vendored
django-pg8000 backend.
"""
from __future__ import annotations

import os
import sys
import traceback

probe_root = "/home/default/django_probe"
vendor_dir = "/home/default/django_probe/vendor"
results_dir = "/home/default/django_probe/results"

for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

os.makedirs(results_dir, exist_ok=True)
os.environ["DJANGO_SETTINGS_MODULE"] = "testsite.settings_postgres"

import django
django.setup()

from io import StringIO

from django.core.management import call_command
from django.db.models import Avg, Count

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: SUCCESS{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


print("=== Probe 7: Django ORM + PostgreSQL ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Django: {django.VERSION}")
results.append(f"  Settings: {os.environ['DJANGO_SETTINGS_MODULE']}")

from django.conf import settings
db_conf = settings.DATABASES["default"]
results.append(f"  Engine: {db_conf['ENGINE']}")
results.append(f"  Database: {db_conf['NAME']}@{db_conf['HOST']}:{db_conf['PORT']}")

section("Migrate")
try:
    out = StringIO()
    call_command("migrate", verbosity=1, stdout=out)
    migrate_output = out.getvalue()
    ok("migrate")
    for line in migrate_output.strip().split("\n")[-5:]:
        results.append(f"    {line}")
except Exception:
    fail("migrate")

section("CRUD operations")
try:
    from testapp.models import Task

    t = Task.objects.create(title="PG probe task", done=False)
    ok("CREATE", f"id={t.id}, title='{t.title}'")

    fetched = Task.objects.get(id=t.id)
    ok("READ", f"title='{fetched.title}', done={fetched.done}")

    fetched.done = True
    fetched.save()
    updated = Task.objects.get(id=t.id)
    ok("UPDATE", f"done={updated.done}")

    count = Task.objects.count()
    ok("COUNT", f"{count} task(s) in database")

    updated.delete()
    remaining = Task.objects.count()
    ok("DELETE", f"{remaining} task(s) remaining")
except Exception:
    fail("CRUD")

section("Built-in auth model")
try:
    from django.contrib.auth.models import User

    User.objects.create_user("pg_probeuser", "pgprobe@test.local", "probe123")
    user_count = User.objects.count()
    ok("Create user", f"{user_count} user(s)")
    User.objects.filter(username="pg_probeuser").delete()
    ok("Delete user")
except Exception:
    fail("Auth model")

section("QuerySet operations")
try:
    from testapp.models import Task

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
    agg = Task.objects.aggregate(
        total=Count("id"),
        done_count=Count("id", filter=django.db.models.Q(done=True)),
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
    ok("first/last", f"first='{first.title}', last='{last.title}'")
except Exception:
    fail("first/last")

section("Cleanup")
try:
    deleted_count, _ = Task.objects.all().delete()
    ok("delete all tasks", f"{deleted_count} removed")
except Exception:
    fail("cleanup")

section("System check")
try:
    out = StringIO()
    call_command("check", stdout=out)
    check_output = out.getvalue().strip()
    ok("check", check_output)
except Exception:
    fail("check")

for _qs_name in ("done_tasks", "not_done"):
    try:
        del globals()[_qs_name]
    except KeyError:
        pass

from django.db import connection as _django_conn
try:
    _django_conn.close()
except Exception:
    pass

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe7_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 7 ===")
