#!/usr/bin/env python
"""
Probe 6: Raw pg8000 PostgreSQL connectivity
Tests whether vendored pg8000 can connect to ChoreBoy's PostgreSQL,
run queries, and perform CRUD -- independent of Django.
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

results = []

PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "postgres"


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


print("=== Probe 6: Raw pg8000 PostgreSQL Connectivity ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")

section("pg8000 import")
try:
    import pg8000
    import pg8000.native
    ok("pg8000", getattr(pg8000, "__version__", "imported"))
except Exception:
    fail("pg8000")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print("\n=== END Probe 6 (early exit -- pg8000 import failed) ===")
    sys.exit(1)

try:
    import scramp
    ok("scramp", getattr(scramp, "__version__", "imported"))
except Exception:
    fail("scramp")

try:
    import dateutil
    ok("python-dateutil", getattr(dateutil, "__version__", "imported"))
except Exception:
    fail("python-dateutil")

section("TCP connection")
conn = None
try:
    conn = pg8000.native.Connection(
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
    )
    ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")
except Exception:
    fail("connect")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print("\n=== END Probe 6 (early exit -- connection failed) ===")
    sys.exit(1)

section("Basic queries")
try:
    rows = conn.run("SELECT version()")
    pg_version = rows[0][0] if rows else "unknown"
    ok("SELECT version()", pg_version[:80])
except Exception:
    fail("SELECT version()")

try:
    rows = conn.run("SELECT 1")
    ok("SELECT 1", f"returned {rows[0][0]}")
except Exception:
    fail("SELECT 1")

try:
    rows = conn.run("SELECT current_database(), current_user")
    ok("current_database/user", f"db={rows[0][0]}, user={rows[0][1]}")
except Exception:
    fail("current_database/user")

section("Create probe database")
try:
    existing = conn.run("SELECT 1 FROM pg_database WHERE datname = 'django_probe'")
    if existing:
        ok("django_probe db", "already exists")
    else:
        conn.run("COMMIT")
        conn.run(
            "CREATE DATABASE django_probe "
            "ENCODING 'UTF8' "
            "TEMPLATE template0 "
            "LC_COLLATE 'C' LC_CTYPE 'C'"
        )
        ok("django_probe db", "created with UTF8 encoding")
except Exception:
    fail("CREATE DATABASE django_probe")

section("CRUD with temp table")
try:
    conn.run(
        "CREATE TEMP TABLE probe6_test ("
        "  id SERIAL PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  value INTEGER NOT NULL"
        ")"
    )
    ok("CREATE TEMP TABLE", "probe6_test")
except Exception:
    fail("CREATE TEMP TABLE")

try:
    conn.run("INSERT INTO probe6_test (name, value) VALUES (:name, :val)",
             name="alpha", val=10)
    conn.run("INSERT INTO probe6_test (name, value) VALUES (:name, :val)",
             name="beta", val=20)
    conn.run("INSERT INTO probe6_test (name, value) VALUES (:name, :val)",
             name="gamma", val=30)
    ok("INSERT", "3 rows")
except Exception:
    fail("INSERT")

try:
    rows = conn.run("SELECT id, name, value FROM probe6_test ORDER BY id")
    ok("SELECT", f"{len(rows)} rows returned")
    for row in rows:
        results.append(f"    id={row[0]}, name={row[1]}, value={row[2]}")
except Exception:
    fail("SELECT")

try:
    conn.run("UPDATE probe6_test SET value = :val WHERE name = :name",
             val=99, name="beta")
    rows = conn.run("SELECT value FROM probe6_test WHERE name = 'beta'")
    ok("UPDATE", f"beta.value now {rows[0][0]}")
except Exception:
    fail("UPDATE")

try:
    conn.run("DELETE FROM probe6_test WHERE name = :name", name="gamma")
    rows = conn.run("SELECT count(*) FROM probe6_test")
    ok("DELETE", f"{rows[0][0]} rows remaining")
except Exception:
    fail("DELETE")

section("Transaction behavior")
try:
    conn.run("BEGIN")
    conn.run("INSERT INTO probe6_test (name, value) VALUES (:name, :val)",
             name="rollback_me", val=0)
    conn.run("ROLLBACK")
    rows = conn.run("SELECT count(*) FROM probe6_test WHERE name = 'rollback_me'")
    count = rows[0][0]
    if count == 0:
        ok("ROLLBACK", "row correctly absent after rollback")
    else:
        results.append(f"  ROLLBACK: UNEXPECTED ({count} rows found)")
except Exception:
    fail("ROLLBACK")

try:
    conn.run("BEGIN")
    conn.run("INSERT INTO probe6_test (name, value) VALUES (:name, :val)",
             name="commit_me", val=42)
    conn.run("COMMIT")
    rows = conn.run("SELECT count(*) FROM probe6_test WHERE name = 'commit_me'")
    count = rows[0][0]
    if count == 1:
        ok("COMMIT", "row persisted after commit")
    else:
        results.append(f"  COMMIT: UNEXPECTED ({count} rows found)")
except Exception:
    fail("COMMIT")

section("Connection close")
try:
    conn.close()
    ok("close", "connection closed cleanly")
except Exception:
    fail("close")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe6_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 6 ===")
