#!/usr/bin/env python
"""
Probe 4 (JNI): JDBC PostgreSQL Connectivity

Tests whether JdbcProbe.class can connect to the CA PostgreSQL database
via JDBC, running inside the in-process JVM via JNI.

Replaces the original probe4_jdbc_connect.py which used subprocess
(blocked on ChoreBoy by mandatory access control).
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

sys.path.insert(0, probe_root)

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

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


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def write_results():
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe4_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 4 (JNI): JDBC PostgreSQL Connectivity ===\n")

results.append("[Configuration]")
results.append(f"  Host: {PG_HOST}")
results.append(f"  Port: {PG_PORT}")
results.append(f"  User: {PG_USER}")
results.append(f"  Database: {PG_DATABASE}")

section("1. Boot JVM via jni_helper")
try:
    import jni_helper
    jvm_ptr, env_ptr = jni_helper.ensure_jvm(probe_root)
    ok("JVM ready")
except Exception as e:
    info(f"JVM boot failed: {e}")
    info(traceback.format_exc())
    write_results()
    print("\n=== END Probe 4 (JVM boot failed) ===")
    raise SystemExit(1)

section("2. JDBC connection test")
try:
    output = jni_helper.call_java_main(
        env_ptr, "JdbcProbe",
        [PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE]
    )

    for line in output.splitlines():
        parts = line.split("|", 1)
        tag = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""

        if tag.endswith("_OK"):
            ok(tag.replace("_OK", ""), detail)
        elif tag.endswith("_FAIL"):
            results.append(f"  {tag}: {detail}")
        else:
            results.append(f"  {line}")

except Exception as e:
    info(f"JdbcProbe.main() failed: {e}")
    info(traceback.format_exc())

    section("Troubleshooting")
    results.append("  - Is PostgreSQL running?")
    results.append("  - Are credentials correct? Edit PG_* values at the top of this probe.")
    results.append(f"  - Does database '{PG_DATABASE}' exist?")

section("SUMMARY")
has_connect = any("JDBC_CONNECT: YES" in r for r in results)
has_version = any("JDBC_VERSION: YES" in r for r in results)
if has_connect and has_version:
    results.append("  JDBC connectivity confirmed via JNI.")
elif has_connect:
    results.append("  JDBC connection succeeded but version query had issues.")
else:
    results.append("  JDBC connection could not be established.")
    results.append("  This is non-fatal for static report testing (probes 5-6).")

write_results()
print("\n=== END Probe 4 ===")
