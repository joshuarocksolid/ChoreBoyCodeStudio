#!/usr/bin/env python
"""
Probe 8: PostgreSQL performance benchmark
Benchmarks raw pg8000 and Django ORM operations against PostgreSQL,
then compares with SQLite equivalents to characterize performance.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

probe_root = "/home/default/django_probe"
vendor_dir = "/home/default/django_probe/vendor"
results_dir = "/home/default/django_probe/results"

for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

os.makedirs(results_dir, exist_ok=True)

results = []
benchmarks = []

RAW_ITERS = 1000
ORM_ITERS = 500

PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "django_probe"


def section(title):
    results.append(f"\n[{title}]")


def bench(label, backend, elapsed, ops):
    ops_sec = ops / elapsed if elapsed > 0 else 0
    avg_ms = (elapsed / ops * 1000) if ops > 0 else 0
    row = {
        "label": label,
        "backend": backend,
        "ops": ops,
        "elapsed": elapsed,
        "ops_sec": ops_sec,
        "avg_ms": avg_ms,
    }
    benchmarks.append(row)
    results.append(
        f"  {label}: {ops} ops in {elapsed:.4f}s "
        f"({ops_sec:,.0f} ops/s, {avg_ms:.3f} ms/op)"
    )


print("=== Probe 8: PostgreSQL Performance Benchmark ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Raw iterations: {RAW_ITERS}")
results.append(f"  ORM iterations: {ORM_ITERS}")

section("Raw pg8000 benchmarks")
try:
    import pg8000
    import pg8000.native

    conn = pg8000.native.Connection(
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
    )
    results.append(f"  Connected to {PG_DATABASE}")

    t0 = time.perf_counter()
    for _ in range(RAW_ITERS):
        conn.run("SELECT 1")
    bench("pg8000 SELECT 1", "postgres", time.perf_counter() - t0, RAW_ITERS)

    conn.run(
        "CREATE TEMP TABLE bench_raw ("
        "  id SERIAL PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  value INTEGER NOT NULL"
        ")"
    )

    t0 = time.perf_counter()
    for i in range(ORM_ITERS):
        conn.run(
            "INSERT INTO bench_raw (name, value) VALUES (:name, :val)",
            name=f"item_{i}",
            val=i,
        )
    bench("pg8000 INSERT", "postgres", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        conn.run("SELECT id, name, value FROM bench_raw LIMIT 50")
    bench("pg8000 SELECT (50 rows)", "postgres", time.perf_counter() - t0, ORM_ITERS)

    conn.close()
except Exception:
    results.append(f"  pg8000 benchmark FAILED\n{traceback.format_exc()}")

section("Django ORM + PostgreSQL benchmarks")
try:
    os.environ["DJANGO_SETTINGS_MODULE"] = "testsite.settings_postgres"

    import django
    django.setup()

    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("migrate", verbosity=0, stdout=out)
    results.append(f"  Migrations applied")

    from testapp.models import Task

    Task.objects.all().delete()

    t0 = time.perf_counter()
    for i in range(ORM_ITERS):
        Task.objects.create(title=f"pg_bench_{i}", done=(i % 2 == 0))
    bench("Django ORM create()", "postgres", time.perf_counter() - t0, ORM_ITERS)

    Task.objects.all().delete()

    t0 = time.perf_counter()
    batch = [Task(title=f"pg_bulk_{i}", done=(i % 2 == 0)) for i in range(ORM_ITERS)]
    Task.objects.bulk_create(batch, batch_size=100)
    bench("Django ORM bulk_create()", "postgres", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        list(Task.objects.filter(done=True)[:50])
    bench("Django ORM filter()", "postgres", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        Task.objects.count()
    bench("Django ORM count()", "postgres", time.perf_counter() - t0, ORM_ITERS)

    from django.db.models import Q

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        Task.objects.filter(Q(done=True) | Q(title__startswith="pg_bulk_1")).count()
    bench("Django ORM complex filter", "postgres", time.perf_counter() - t0, ORM_ITERS)

    Task.objects.all().delete()
    results.append(f"  Postgres cleanup done")
except Exception:
    results.append(f"  Django+Postgres benchmark FAILED\n{traceback.format_exc()}")

section("Django ORM + SQLite benchmarks (comparison)")
try:
    from django.conf import settings

    settings.DATABASES["sqlite_bench"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(probe_root, "probe_bench.sqlite3"),
    }

    from django.db import connections

    out = StringIO()
    call_command("migrate", database="sqlite_bench", verbosity=0, stdout=out)
    results.append(f"  SQLite migrations applied")

    SQ = "sqlite_bench"

    Task.objects.using(SQ).all().delete()

    t0 = time.perf_counter()
    for i in range(ORM_ITERS):
        Task(title=f"sq_bench_{i}", done=(i % 2 == 0)).save(using=SQ)
    bench("Django ORM create()", "sqlite", time.perf_counter() - t0, ORM_ITERS)

    Task.objects.using(SQ).all().delete()

    t0 = time.perf_counter()
    batch = [Task(title=f"sq_bulk_{i}", done=(i % 2 == 0)) for i in range(ORM_ITERS)]
    Task.objects.using(SQ).bulk_create(batch, batch_size=100)
    bench("Django ORM bulk_create()", "sqlite", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        list(Task.objects.using(SQ).filter(done=True)[:50])
    bench("Django ORM filter()", "sqlite", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        Task.objects.using(SQ).count()
    bench("Django ORM count()", "sqlite", time.perf_counter() - t0, ORM_ITERS)

    t0 = time.perf_counter()
    for _ in range(ORM_ITERS):
        Task.objects.using(SQ).filter(Q(done=True) | Q(title__startswith="sq_bulk_1")).count()
    bench("Django ORM complex filter", "sqlite", time.perf_counter() - t0, ORM_ITERS)

    Task.objects.using(SQ).all().delete()
    connections["sqlite_bench"].close()
    results.append(f"  SQLite cleanup done")

    bench_db = os.path.join(probe_root, "probe_bench.sqlite3")
    if os.path.exists(bench_db):
        os.unlink(bench_db)

except Exception:
    results.append(f"  Django+SQLite benchmark FAILED\n{traceback.format_exc()}")

section("Summary table")
results.append("")
results.append(f"  {'Operation':<30} {'Backend':<10} {'Ops':>6} {'Total(s)':>10} {'Ops/s':>10} {'ms/op':>8}")
results.append(f"  {'-'*30} {'-'*10} {'-'*6} {'-'*10} {'-'*10} {'-'*8}")
for b in benchmarks:
    results.append(
        f"  {b['label']:<30} {b['backend']:<10} {b['ops']:>6} "
        f"{b['elapsed']:>10.4f} {b['ops_sec']:>10,.0f} {b['avg_ms']:>8.3f}"
    )

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe8_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 8 ===")
