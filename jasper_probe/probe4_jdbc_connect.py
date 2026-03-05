#!/usr/bin/env python
"""
Probe 4: JDBC PostgreSQL Connectivity
Tests whether Java can connect to the CA PostgreSQL database via JDBC.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

DISCOVERED_PATH = os.path.join(probe_root, "_discovered.json")

PG_HOST = "localhost"
PG_PORT = "5432"
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "classicaccounting"

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


def bail(msg):
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe4_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 4 ({msg}) ===")
    raise SystemExit(1)


print("=== Probe 4: JDBC PostgreSQL Connectivity ===\n")

results.append("[Configuration]")
results.append(f"  Host: {PG_HOST}")
results.append(f"  Port: {PG_PORT}")
results.append(f"  User: {PG_USER}")
results.append(f"  Database: {PG_DATABASE}")

if not os.path.exists(DISCOVERED_PATH):
    results.append("\n  ERROR: _discovered.json not found. Run probes 1-2 first.")
    bail("no discovery file")

with open(DISCOVERED_PATH) as f:
    discovered = json.load(f)

java_path = discovered.get("java_path")
classpath = discovered.get("classpath")

if not java_path:
    results.append("\n  ERROR: No java_path. Run probe 1 first.")
    bail("no java_path")

if not classpath:
    results.append("\n  ERROR: No classpath. Run probe 2 first.")
    bail("no classpath")

section("JDBC connection test")
try:
    r = subprocess.run(
        [java_path, "-cp", classpath, "JdbcProbe",
         PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE],
        capture_output=True, text=True, timeout=30
    )

    results.append(f"  Exit code: {r.returncode}")

    for line in r.stdout.strip().splitlines():
        parts = line.split("|", 1)
        tag = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""

        if tag.endswith("_OK"):
            ok(tag.replace("_OK", ""), detail)
        elif tag.endswith("_FAIL"):
            results.append(f"  {tag}: {detail}")
        else:
            results.append(f"  {line}")

    if r.stderr.strip():
        section("stderr")
        for line in r.stderr.strip().splitlines()[:10]:
            results.append(f"  {line}")

    if r.returncode != 0:
        section("Troubleshooting")
        results.append("  - Is PostgreSQL running? Check: pg_isready or service postgresql status")
        results.append("  - Are credentials correct? Edit PG_* values at the top of this probe.")
        results.append(f"  - Does database '{PG_DATABASE}' exist?")

except subprocess.TimeoutExpired:
    results.append("  RESULT: JDBC connection timed out (30s)")
    results.append("  PostgreSQL may not be running or port may be blocked.")
except Exception:
    fail("subprocess.run")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe4_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 4 ===")
